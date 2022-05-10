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

## Data Replication - Benchmark Execution

### Operations on dbt2-client

Start a new SSH session to the `dbt2-client` machine:

```shell
$ ssh -i ssh-id_rsa rocky@<dbt2-client-public-ip>
```

Start DBT2 client with 48 connections to `proxy1`:

```shell
$ sudo su - dbt2
$ mkdir dbt2-output
$ screen
$ dbt2-client \
      -d <proxy1-private-ip> \
      -c 48 \
      -l 6432 \
      -b edb \
      -o ./dbt2-output
```

### Operations on dbt2-driver

Once the `dbt2-client` program is running and all its database connections are
ready, we can proceed with the following.

Start a new SSH session to the `dbt2-driver` machine:

```shell
$ ssh -i ssh-id_rsa rocky@<dbt2-driver-public-ip>
```

Start the script in charge of generating the database load:
```shell
$ sudo su - dbt2
$ screen
$ python3 ./dbt2-driver-rampup.py \
      --client <dbt2-client-private-ip> \
      -d 120 \
      -w 5000 \
      -s 1 \
      -m 120 \
      -S 1 \
      --pg "host=<bdr1-private-ip> port=5444 user=dbt2 password=<dbt2-user-password> dbname=edb"
```
#### Notes

`dbt2-driver-rampup.py` arguments:
- `--client`: private IP address of the DBT2 client machine
- `-d`: test duration in second, for each iteration
- `-w`: number of wharehouses. Must match the value defined in
  `configuration.yml`
- `-s`: starting number of terminals
- `-m`: maximum number of terminals
- `-S`: increment the number of terminals by this value, for each iteration
- `--pg`: PG connection string to `bdr1`

`<dbt2-user-password>` can be found on the machine used to provision and deploy the environment with:
```shell
$ cat ~/.edb/dbt2_pass
```

### Results

`dbt2-driver-rampup.py` displays on its output the results, for each number of
terminals, in CSV format.

Example:
```csv
timestamp,terminals,notpm,bdr2_catchup_time,bdr2_sustainable_notpm,bdr3_catchup_time,bdr3_sustainable_notpm,bdr4_catchup_time,bdr4_sustainable_notpm
2022-05-12T11:20:17.849810,5,56089.41,0.005599,56086.793083712706,0.005609,56086.78841003174,0.005605,56086.790279504035
2022-05-12T11:22:35.429308,10,106050.25,0.104732,105957.77358713893,0.104740,105957.76652944754,0.104736,105957.77005829311
2022-05-12T11:25:00.939351,15,144269.24,0.103717,144144.65457384638,0.409874,143778.14895811616,0.307712,143900.24140763312
```

## Failover & Switchover - Benchmark Execution

**TODO**
