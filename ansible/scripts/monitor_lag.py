"""
Replication lag monitoring script for BDR cluster producing CSV output

Ex:

$ sudo -u enterprisedb python ./monit_tps_replication_lag.py  "host=/tmp dbname=bdrdb" /tmp/output.csv
"""

import glob
import os
import psycopg2
import sys
import time
from datetime import datetime

def usage():
    sys.exit("Usage: %s \"<POSTGRESQL_CONN_STRING>\" <OUTPUT_FILE>" % sys.argv[0])


def get_pg_data(conn):
    """
    Get current Postgres data directory
    """
    cur = conn.cursor()
    cur.execute("SHOW data_directory")
    r = cur.fetchone()
    cur.close()
    return r[0]


def monitor_spill_files(pg_data):
    """
    Returns the total number and total size of .spill files found in
    PGDATA/pg_replslot/*
    """
    n = 0
    s = 0
    for f in glob.glob(os.path.join(pg_data, 'pg_replslot', '*', '*.spill')):
        n += 1
        s += os.path.getsize(f)
    return (n, s)


def main():

    if len(sys.argv) != 3:
        usage()

    try:
        conn = psycopg2.connect(sys.argv[1])
        conn.set_session(autocommit=True)
    except psycopg2.Error as e:
        sys.exit("Unable to connect to the database")

    try:
        pg_data = get_pg_data(conn)
    except psycopg2.Error as e:
        sys.exit("Unable to get Postgres data directory")

    last_no_xact = 0
    snapshot_timestamp = None
    bdr_nodes = []

    output = sys.argv[2]
    output_exists = os.path.exists(output)

    i = 0
    while True:
        i += 1
        line = []
        # Starting time
        start = datetime.now()
        # Get number and total size of .spill files
        (sf, sf_size) = monitor_spill_files(pg_data)

        cur = conn.cursor()
        cur.execute("""
            SELECT
                now() AS timestamp,
                (SELECT
                    SUM(pg_stat_get_db_xact_commit(oid)+pg_stat_get_db_xact_rollback(oid))::BIGINT
                 FROM pg_database
                 WHERE datname = current_database()
                ) AS no_xact,
                json_object_agg(target_name, replay_lag_bytes) AS nodes_replay_lag_bytes,
                json_object_agg(target_name, (SELECT EXTRACT(epoch FROM ct.catchup_time) FROM bdr_monitor_repl_catchup_time() AS ct WHERE ct.bdr_slot_name=bdr.node_slots.slot_name)) AS nodes_replay_lag_bytes,
                pg_current_wal_lsn()
            FROM bdr.node_slots
            WHERE origin_name <> '' AND slot_type = 'logical';
        """)
        r = cur.fetchone()
        if i == 1:
            # First iteration of the loop: just display columns headers

            # Let sort BDR node list
            for k in sorted(r[2]):
                bdr_nodes.append(k)

            line.append("timestamp")
            line.append("tps")
            for n in bdr_nodes:
                line.append("%s_lag_bytes" % n )
            for n in bdr_nodes:
                line.append("%s_catchup_time" % n )
            line.append("LSN")
            line.append("spill_files")
            line.append("spill_files_size")
        else:
            # Timestamp
            line.append(r[0].strftime("%Y-%m-%d %H:%M:%S.%f"))
            # Duration ins second between each snapshot
            d = (r[0] - snapshot_timestamp).total_seconds()
            # TPS
            line.append("%.2f" % ((r[1] - last_no_xact) / d))
            # Replication lag in bytes
            for n in bdr_nodes:
                line.append("%d" % r[2][n])
            # Catchup time
            for n in bdr_nodes:
                line.append("%f" % float(r[3][n]))
            line.append(r[4])
            # .spill files metrics
            line.append("%s" % sf)
            line.append("%s" % sf_size)


        # Record some informations needed for the next loop iteration
        snapshot_timestamp = r[0]
        last_no_xact = r[1]

        cur.close()

        with open(output, 'a') as f:
            # Do not write CSV headers if the output file already exist
            if not (i == 1 and output_exists):
                f.write("%s\n" % ';'.join(line))

        end = datetime.now()
        duration = (end - start).total_seconds()
        sleep_time = 30 - duration
        # Wait for (30 - duration) seconds until next iteration
        if sleep_time > 0:
            time.sleep(30 - duration)


if __name__ == "__main__":
    main()
