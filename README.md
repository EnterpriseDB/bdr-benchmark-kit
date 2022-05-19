# bdr-benchmark-kit

BDR Benchmark Kit based on Terraform and Ansible

## Prerequisites

The following components must be installed on the system:
- Python3
- AWS CLI
- Ansible
- Terraform
- TPAexec

### Prequisites installation on Debian11

#### Python3/pip3

```console
$ sudo apt install python3 python3-pip -y
$ sudo pip3 install pip --upgrade
```

#### AWS CLI

```console
$ sudo pip3 install awscli
```

AWS Access Key and Secret Access Key configuration:
```console
$ aws configure
```

#### Ansible

```console
$ sudo pip3 install ansible-core
```

#### Terraform

```console
$ sudo apt install unzip -y
$ wget https://releases.hashicorp.com/terraform/1.1.9/terraform_1.1.9_linux_amd64.zip
$ unzip terraform_1.1.9_linux_amd64.zip
$ sudo install terraform /usr/bin
```

#### TPAexec

Please refer to TPAexec installation guide.

## BDR environment provisioing and deployment on AWS

In order to provision the required resources on AWS, this repository should be
cloned:

```console
$ cd $HOME
$ git clone https://github.com/EnterpriseDB/bdr-benchmark-kit.git
$ cd bdr-benchmark-kit
```

### Target AWS infrastructure

Depending on the choice of the BDR Always-ON architecture (`gold` or `silver`),
2 files are used to describe the target AWS infrastrures:
- [`silver-infrastructure.yml`](./silver-infrastructure.yml)
- [`gold-infrastructure.yml`](./gold-infrastructure.yml)

#### Default Silver Infrastructure

| Object        | Configuration                                                          |
| ------------- | ---------------------------------------------------------------------- |
| Region        | `us-east-1`                                                            |
| OS            | Rocky 8.4                                                              |
| BDR servers   | 2 x `c5d.12xlarge` in `us-east-1b`, 1 x `c5d.12xlarge` in `us-east-1c` |
| Proxy servers | 2 x `c5.9xlarge` in `us-east-1b` and `us-east-1c`                      |
| Barman server | 1 x `c5.2xlarge` + `3TB` of additional storage in `us-east-1b`         |
| DBT2 client   | 1 x `c5.18xlarge` in `us-east-1b`                                      |
| DBT2 driver   | 1 x `c5.18xlarge` in `us-east-1b`                                      |

#### Default Gold Infrastructure

| Object        | Configuration                                                                   |
| ------------- | ------------------------------------------------------------------------------- |
| Regions       | `us-east-1`, `us-east-2` and `us-west-1`                                        |
| OS            | Rocky 8.4                                                                       |
| BDR servers   | 4 x `c5d.12xlarge` in `us-east-1b`, `us-east-1c`, `us-east-2a` and `us-east-2b` |
| BDR witness   | 1 x `c5.4xlarge` in `us-west-1b`                                                |
| Proxy servers | 4 x `c5.9xlarge` in `us-east-1b`, `us-east-1c`, `us-east-2a`, `us-east-2b`      |
| Barman server | 1 x `c5.2xlarge` + `3TB` of additional storage in `us-east-1b`                  |
| DBT2 client   | 1 x `c5.18xlarge` in `us-east-1b`                                               |
| DBT2 driver   | 1 x `c5.18xlarge` in `us-east-1b`                                               |

### Deployment Configuration

The most important settings are accessible through the `configuration.yml`
file. This file should be updated according to your requirements. The following
variables **must** be set:
- `repo_username`: EDB package repository username
- `repo_password`: EDB package repository password
- `tpa_subscription_token`: EDB subscription token

Depending on how and where TPAexec has been installed, `tpa_bin_path` could be
updated.

By default, the number of TPC-C warehouses is set to `5000`, leading to
produce around 500GB of data and indexes. To change the number of warehouses,
the variable `dbt2_warehouse` should be used.

**Default Postgres flavour is EPAS in version 14.**

### Cloud Resources Creation and Deployment

Once the `configuration.yml` file has been updated and the target
infrastructure file adapted (not mandatory), it's now time to proceed with
cloud resources creation:

  1. A new *project* must be created with the help of the `new-project.py`
     script. This script is in charge of creating a dedicated directory for the
     *project*, generating SSH keys, building Terraform configuration based on
     the infrastructure file, copying Ansible and Terraform code into the
     *project* directory.

     First argument is the *project* path, second argument is the
     path to the infrastructure file:
     ```shell
     $ python3 ~/bdr-benchmark-kit/scripts/new-project.py \
           ~/my_benchmark \
           ~/bdr-benchmark-kit/gold-infrastructure.yml
     ```

  2. Terraform initialisation of the *project*:
     ```shell
     $ cd ~/my_benchmark
     $ terraform init
     ```

  3. Apply resources creation:
     ```shell
     $ cd ~/my_benchmark
     $ terraform apply \
           -var-file=./terraform_vars.json \
           -auto-approve
     ```

When the Cloud resources are ready, the next step is software deployment.

  4. Execute pre-deployment operations: building TPAexec `config.yml` and
     Ansible inventory file, generate the `deploy.sh` script, etc.. Depending
     on the target BDR architecture, the `-a` option must be set to `silver` or
     `gold`.

     First argument is the *project* path, second argument is the
     `configuration.yml` path.

     Usage example:
     ```shell
     $ python3 ~/bdr-benchmark-kit/scripts/pre-deploy.py \
           -a gold \
           ~/my_benchmark \
           ~/bdr-benchmark-kit/configuration.yml
     ```

  5. Execute the deployment script:
     ```shell
     $ cd ~/my_benchmark
     $ ./deploy.sh
     ```

### SSH access to the machines

Once the deployment is completed, machines public and private IPs are stored in
the `servers.yml` file.

Example:

```yaml
---
servers:
  barman1:
    type: barman
    region: us-east-1
    az: us-east-1b
    public_ip: 54.166.46.2
    private_ip: 10.0.0.103
    public_dns: ec2-54-166-46-2.compute-1.amazonaws.com
  bdr1:
    type: bdr
    region: us-east-1
    az: us-east-1b
    public_ip: 3.80.202.134
    private_ip: 10.0.0.148
    public_dns: ec2-3-80-202-134.compute-1.amazonaws.com
[...]
```

SSH keys are stored in `ssh-id_rsa` and `ssh-id_rsa.pub`.

## Replication modes

### Asynchronous replication

By default, data replication is configured in asynchronous mode.

### Quorum based synchronous replication

Enabling quorum based synchronous replication, in the Gold layout, can be
achieved by updating Postgres configuration on `bdr1` as following:
```sql
edb=# ALTER SYSTEM SET synchronous_standby_names TO 'FIRST 1 (bdr_edb_bdrdb_group_bdr1_bdr2, bdr_edb_bdrdb_group_bdr1_bdr3, bdr_edb_bdrdb_group_bdr1_bdr4)';
edb=# SELECT pg_reload_conf();
```

### Asynchronous replication with BDR Lag Control

The following configuration enables BDR Lag Control:
```sql
edb=# ALTER SYSTEM SET bdr.lag_control_min_conforming_nodes TO '4';
edb=# ALTER SYSTEM SET bdr.lag_control_max_commit_delay TO '60000';
edb=# ALTER SYSTEM SET bdr.lag_control_max_lag_size TO '1.5GB';
edb=# SELECT pg_reload_conf();
```

## Data Replication - Benchmark Execution

### Operations on dbt2-driver

Start a new SSH session to the `dbt2-driver` machine:

```shell
$ ssh -i ssh-id_rsa rocky@<dbt2-driver-public-ip>
```

Start the script in charge of generating the database load:
```shell
$ sudo su - dbt2
$ screen
$ python3 ./dbt2-driver-rampup.py \
      -c <dbt2-client-private-ip> \
      -d 120 \
      -w 5000 \
      -s 1 \
      -m 71 \
      -S 3 \
      -P <proxy1-private-ip> \
      --pg "host=<bdr1-private-ip> port=5444 user=dbt2 dbname=edb"
```

#### Notes

`dbt2-driver-rampup.py` arguments:
- `-c`: private IP address of the DBT2 client machine
- `-d`: test duration in second, for each iteration
- `-w`: number of wharehouses. Must match the value defined in
  `configuration.yml`
- `-s`: starting number of terminals
- `-m`: maximum number of terminals
- `-S`: increment the number of terminals by this value, for each iteration
- `-P`: Harp proxy node private IP
- `--pg`: PG connection string to `bdr1`

### Results

`dbt2-driver-rampup.py` displays on its output the results, for each number of
terminals, in CSV format.

Example:
```csv
timestamp,terminals,notpm,bdr2_catchup_time,bdr2_sustainable_notpm,bdr3_catchup_time,bdr3_sustainable_notpm,bdr4_catchup_time,bdr4_sustainable_notpm
2022-05-19T07:09:28.333929,1,10813.61,0.005883,10813.079888758453,0.005964,10813.072590292262,0.005973,10813.071779352184
2022-05-19T07:11:40.596692,4,33318.31,0.001876,33317.78913189657,0.001897,33317.78330137564,0.001906,33317.78080258158
2022-05-19T07:14:05.854092,7,52895.29,0.005094,52893.0446902529,0.005150,52893.02000789133,0.005159,52893.01604108537
2022-05-19T07:16:39.027928,10,70323.03,0.001565,70322.11288244449,0.001589,70322.09881820815,0.001597,70322.0941301306
2022-05-19T07:19:15.204003,13,85270.68,1.023976,84549.21031515274,0.310567,85050.5641786228,0.002855,85268.65131667076
```

## Failover & Switchover - Benchmark Execution

Downtime, from an application point of view, is measured by the
`downtime-checker.py` script. This script is in charge of inserting records
into a table containing the name of BDR node the script is connected to, and
the current timestamp. In addition, it's able to generate additional traffic
based on the DBT2 kit.


This script must be executed from the `dbt2-driver` machine:
```shell
$ sudo su - dbt2
$ screen
# With additional traffic/load generated by DBT2
$ python3 downtime-checker.py \
  --pg "host=<proxy1-private-ip> dbname=edb port=6432" \
  -T -c <dbt2-client-private-ip> \
  -P <proxy1-private-ip> \
  -w 5000
```

```shell
# Or without additional traffic
$ python3 downtime-checker.py \
  --pg "host=<proxy1-private-ip> dbname=edb port=6432"
```

Once the script is running, we can proceed with the following to trigger a
switchover or a failover.

### Switchover

To trigger a switchover operation, on the `bdr1` machine:
```shell
$ sudo harpctl promote bdr2
```

Example:
```shell
[dbt2@ip-10-0-0-199 ~]$ python3 downtime-checker.py \
    --pg "host=10.0.0.123 dbname=edb port=6432" \
    -T \
    -c 10.0.0.250 \
    -P 10.0.0.123 \
    -w 5000
2022-05-19 20:49:44.140803 INFO: Starting DBT2 client...
2022-05-19 20:49:49.147031 INFO: Starting DBT2 driver...
2022-05-19 20:49:49.148906 INFO: Connecting to PostgreSQL...
2022-05-19 20:49:49.172649 INFO: Connected.
2022-05-19 20:50:04.702920 ERROR: Connection lost
2022-05-19 20:50:04.702956 INFO: Connecting to PostgreSQL...
2022-05-19 20:50:04.728276 INFO: Connected.
Downtime: 0:00:00.061442
```

Once the measurement is done, `bdr1` can re-promoted as the BDR lead master
node with:
```shell
$ sudo harpctl promote bdr1
```

### Failover - Postgres crash

To simulate a Postgres crash incident, the follwing can be executed on the
`bdr1` machine:
```shell
$ sudo killall -9 harp-manager edb-postmaster
```

Once the measurement is done, `bdr1` can be reintegrated to the BDR cluster:
```shell
$ sudo systemctl start harp-manager
# Wait for the end of Postgres recovery
$ sudo harpctl promote bdr1
```

### Failover - System crash

To simulate a System crash incident, the follwing can be executed on the
`bdr1` machine:
```shell
$ sudo -i
$ echo c > /proc/sysrq-trigger
# SSH connection to bdr1 will freeze and the machine is rebooting
```

Once the measurement is done and the machine is up andrunning, `bdr1` can be
reintegrated to the BDR cluster:
```shell
$ sudo harpctl promote bdr1
```
