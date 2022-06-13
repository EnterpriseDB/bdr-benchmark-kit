# coding: utf-8

import argparse
import datetime
import psycopg2
import re
import subprocess
import sys
import tempfile
import time


def exec_driver(client, duration, warehouse, terminal):
    notpm = None
    with tempfile.TemporaryDirectory() as tmpdirname:
        # Execute the dbt2-driver command
        cmd = subprocess.run(
            ['dbt2-driver',
             '-d', client,
             '-l', str(duration),
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
             '-outdir', tmpdirname,
             '-altered', '1',
             '-L', str(terminal)],
             stdout=subprocess.PIPE,
             stderr=subprocess.PIPE,
        )
        if cmd.returncode != 0:
            raise Exception(cmd.stderr.decode('utf-8'))
        # Execute the dbt2-post-process command
        cmd = subprocess.run(
            ['dbt2-post-process', tmpdirname + '/mix.log'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if cmd.returncode != 0:
            raise Exception(cmd.stderr.decode('utf-8'))

        for line in cmd.stdout.splitlines():
            m = re.search(r'^([0-9.]*) new-order transactions per minute', line.decode('utf-8'))
            if m:
                notpm = m.group(1)
    return notpm


def start_dbt2_client(client, host, dbname, port, connections):
    cmd = ' '.join([
        'dbt2-client',
        '-d', host,
        '-c', str(connections),
        '-l', str(port),
        '-b', dbname, '-o', '/home/dbt2'
    ])
    p = subprocess.Popen(
        'ssh %s \'%s\'' % (client, cmd),
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return p


def checkpoint(conn):
    cur = conn.cursor()
    cur.execute("CHECKPOINT");
    cur.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--client', '-c',
        dest='client',
        type=str,
        help="DBT2 client address.",
    )
    parser.add_argument(
        '--duration', '-d',
        dest='duration',
        type=int,
        help="Test duration in seconds. Default: %(default)s",
        default=100,
    )
    parser.add_argument(
        '--warehouse', '-w',
        dest='warehouse',
        type=int,
        help="Number of warehouse. Default: %(default)s",
        default=1000,
    )
    parser.add_argument(
        '--start-terminal', '-s',
        dest='start_terminal',
        type=int,
        help="Starting number of terminal. Default: %(default)s",
        default=1,
    )
    parser.add_argument(
        '--max-terminal', '-m',
        dest='max_terminal',
        type=int,
        help="Maximum number of terminal. Default: %(default)s",
        default=100,
    )
    parser.add_argument(
        '--step', '-S',
        dest='step',
        type=int,
        help="Increase the number of terminal by this value. Default: %(default)s",
        default=1,
    )
    parser.add_argument(
        '--pg',
        dest='pg',
        type=str,
        help="Postgres connection string.",
        default='',
    )
    parser.add_argument(
        '--host', '-H',
        dest='host',
        type=str,
        help="Database address.",
    )
    parser.add_argument(
        '--connections', '-C',
        dest='connections',
        type=int,
        help="Number of DBT2 client connections to the database. Default: %(default)s",
        default=48,
    )
    parser.add_argument(
        '--dbname', '-D',
        dest='dbname',
        default="edb",
        type=str,
        help="Database name. Default: %(default)s",
    )
    parser.add_argument(
        '--port', '-p',
        dest='port',
        type=int,
        help="Database port. Default: %(default)s",
        default=5444,
    )
    env = parser.parse_args()

    try:
        conn = psycopg2.connect(env.pg)
        conn.set_session(autocommit=True)
    except psycopg2.Error as e:
        sys.exit("Unable to connect to the database")

    # Starting dbt2-client
    client = start_dbt2_client(
        env.client, env.host, env.dbname, env.port, env.connections
    )
    # Waiting a moment before starting the driver process: we want to let a
    # decent amount of time to the client to start all the required
    # database connections.
    time.sleep(60)


    i = 0
    for t in range(env.start_terminal, env.max_terminal, env.step):
        # Execute a checkpoint
        checkpoint(conn)
        # Execute dbt2-driver
        notpm = exec_driver(env.client, env.duration, env.warehouse, t)
        timestamp = datetime.datetime.utcnow().isoformat()

        data = {}
        data['timestamp'] = timestamp
        data['terminals'] = t
        data['notpm'] = notpm

        # Display headers on the first iteration
        if i == 0:
            print(','.join(list(data.keys())))
        print(','.join([str(v) for _, v in data.items()]))
        i += 1

    client.kill()
