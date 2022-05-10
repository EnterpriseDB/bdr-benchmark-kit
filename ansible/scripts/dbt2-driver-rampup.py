# coding: utf-8

import argparse
import datetime
import psycopg2
import re
import subprocess
import sys
import tempfile


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


def checkpoint(conn):
    cur = conn.cursor()
    cur.execute("SELECT bdr.run_on_all_nodes('CHECKPOINT')");
    cur.close()

def catchup_time(conn):
    records = []
    cur = conn.cursor()
    cur.execute("""
    SELECT bdr_slot_name, EXTRACT(epoch FROM catchup_time) AS catchup_time
    FROM bdr_monitor_repl_catchup_time() ORDER BY bdr_slot_name
    """)
    for r in cur.fetchall():
        records.append((r[0], r[1]))
    cur.close()
    return records

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
    env = parser.parse_args()

    try:
        conn = psycopg2.connect(env.pg)
        conn.set_session(autocommit=True)
    except psycopg2.Error as e:
        sys.exit("Unable to connect to the database")

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

        # Get catchup time
        for (c_slot_name, c_time) in catchup_time(conn):
            node_name = c_slot_name.replace('bdr_edb_bdrdb_group_', '')

            if node_name.startswith('witness'):
                # Just ignore what's going on with the witness node
                continue

            data['%s_catchup_time' % node_name] = c_time
            # Calculate sustainable rate
            sustainable_rate = (float(notpm)*(float(env.duration)/60))/(float(env.duration) + float(c_time)) * 60
            data['%s_sustainable_notpm' % node_name] = sustainable_rate

        # Display headers on the first iteration
        if i == 0:
            print(','.join(list(data.keys())))
        print(','.join([str(v) for _, v in data.items()]))
        i += 1
