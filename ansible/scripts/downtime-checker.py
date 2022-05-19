# -*- coding: utf-8 -*-

import argparse
import psycopg2
import time
from datetime import datetime as dt
from subprocess import Popen, PIPE

def connect(conn_string):
    while True:
        try:
            print("%s INFO: Connecting to PostgreSQL..." % dt.now())
            conn = psycopg2.connect(conn_string)
            print("%s INFO: Connected." % dt.now())
            return conn
        except psycopg2.Error as e:
            print("%s ERROR: Cannot connect, new try." % dt.now())


def monitor_downtime(conn, pg):
    bdr_leader_init = None
    bdr_leader_current = None
    downtime = None

    while True:
        try:
            cur = conn.cursor()
            # Not leader found yet? then this is the first iteration and we
            # must remove any data from the ping table.
            if bdr_leader_init is None:
                cur.execute("TRUNCATE ping")

            # Get BDR leader name
            if bdr_leader_init is None or bdr_leader_current is None:
                cur.execute("SELECT node_name FROM bdr.local_node_info()")
                r = cur.fetchone()
                if bdr_leader_init is None:
                    bdr_leader_init = r[0]
                if bdr_leader_current is None:
                    bdr_leader_current = r[0]

            # Insert a new record into the ping table
            cur.execute(
                "INSERT INTO ping (bdr_node) VALUES "
                "((SELECT node_name FROM bdr.local_node_info()))"
            )
            conn.commit()

            # If the current BDR leader node is different from the initial one,
            # then this must indicate a new BDR leader node has been promoted.
            if bdr_leader_current != bdr_leader_init:
                cur2 = conn.cursor()
                cur2.execute(
                    "SELECT MIN(timestamp) - ("
                    "  SELECT MAX(timestamp) FROM ping where bdr_node = %s"
                    ") FROM ping WHERE bdr_node = %s",
                    (bdr_leader_init, bdr_leader_current)
                )
                r2 = cur2.fetchone()
                downtime = r2[0]
                conn.commit()
                return downtime

        except psycopg2.OperationalError as e:
            # Connection to the database has been lost, this must be due to a
            # leader change, then we reset bdr_leader_current to None.
            bdr_leader_current = None
            print("%s ERROR: Connection lost" % dt.now())
            conn = connect(pg)
        except psycopg2.DatabaseError as e:
            bdr_leader_current = None
            print(e)
            print("%s ERROR: Cannot insert message" % dt.now())
            conn = connect(pg)


def start_dbt2_client(client, proxy, dbname, port, connections):
    print("%s INFO: Starting DBT2 client..." % dt.now())
    cmd = ' '.join([
        'ssh', client,
        'dbt2-client',
        '-d', proxy,
        '-c', str(connections),
        '-l', str(port),
        '-b', dbname, '-o', '/tmp'
    ])
    p = Popen(
        cmd,
        shell=True,
        stdout=PIPE,
        stderr=PIPE,
    )
    return p


def start_dbt2_driver(client, warehouse, terminal):
    print("%s INFO: Starting DBT2 driver..." % dt.now())
    cmd = ' '.join([
        'dbt2-driver',
        '-d', client,
        '-l', '500',
        '-wmin', '1',
        '-wmax', str(warehouse),
        '-w', str(warehouse),
        '-ktd', '0',
        '-ktn', '0',
        '-kto', '0',
        '-ktp', '0',
        '-kts', '0',
        '-ttd', '0',
        '-ttn', '0',
        '-tto', '0',
        '-ttp', '0',
        '-tts', '0',
        '-outdir', '/tmp',
        '-altered', '1',
        '-L', str(terminal)
    ])
    p = Popen(
        cmd,
        shell=True,
        stdout=PIPE,
        stderr=PIPE,
    )
    return p


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--pg',
        dest='pg',
        type=str,
        help="Postgres connection string to the Harp proxy node.",
        default='',
    )
    parser.add_argument(
        '--traffic', '-T',
        dest='traffic',
        action='store_true',
        default=False,
        help="Generate additional traffic through DBT-2 (TPC-C benchmark kit).",
    )
    parser.add_argument(
        '--client', '-c',
        dest='client',
        type=str,
        help="Additional traffic: DBT2 client address.",
    )
    parser.add_argument(
        '--proxy', '-P',
        dest='proxy',
        type=str,
        help="Additional traffic: Harp proxy address.",
    )
    parser.add_argument(
        '--connections', '-C',
        dest='connections',
        type=int,
        help="Additional traffic: number of DBT2 client connections to "
             "Harp proxy. Default: %(default)s",
        default=12,
    )
    parser.add_argument(
        '--dbname', '-D',
        dest='dbname',
        default="edb",
        type=str,
        help="Additional traffic: Database name. Default: %(default)s",
    )
    parser.add_argument(
        '--port', '-p',
        dest='port',
        type=int,
        help="Additional traffic: Harp proxy port. Default: %(default)s",
        default=6432,
    )
    parser.add_argument(
        '--warehouse', '-w',
        dest='warehouse',
        type=int,
        help="Additional traffic: number of TPC-C warehouse. Default: %(default)s",
        default=5000,
    )
    parser.add_argument(
        '--terminal', '-t',
        dest='terminal',
        type=int,
        help="Additional traffic: number of TPC-C terminals. Default: %(default)s",
        default=12,
    )
    env = parser.parse_args()
    driver = None
    client = None

    if env.traffic:
        # Start the client process
        client = start_dbt2_client(
            env.client, env.proxy, env.dbname, env.port, env.connections
        )
        # Waiting a moment before starting the driver process: we want to let a
        # decent amount of time to the client to start all the required
        # database connections.
        time.sleep(5)
        # Start the driver process
        driver = start_dbt2_driver(
            env.client, env.warehouse, env.terminal
        )

    conn = connect(env.pg)
    downtime = monitor_downtime(conn, env.pg)
    print("Downtime: %s" % downtime)
    conn.close()

    # Stop the DBT2 processes
    if driver:
        driver.kill()
    if client:
        client.kill()


if __name__ == '__main__':
    main()
