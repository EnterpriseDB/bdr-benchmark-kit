# coding: utf-8

import argparse
import json
from pathlib import Path, PurePath
import os
import shutil
import sys
import yaml

from jinja2 import Environment, FileSystemLoader


def render_template(template_name, vars={}):
    # Template directory is located in scripts/templates
    current_dir = Path(__file__).parent.resolve()
    templates_dir = PurePath.joinpath(current_dir, 'templates')

    file_loader = FileSystemLoader(str(templates_dir))
    env = Environment(loader=file_loader, trim_blocks=True)
    template = env.get_template(template_name)

    return template.render(**vars)


def template(template_name, dest, vars={}):
    try:
        content = render_template(template_name, vars)
        with open(dest, 'w') as f:
            f.write(content)
    except Exception as e:
        sys.exit("ERROR: could not render template %s (%s)"
                 % (template_name, e))


def load_yaml(file_path):
    # Load yaml file
    if not os.path.exists(file_path):
        sys.exit("ERROR: file %s not found" % file_path)
    try:
        with open(file_path) as f:
            return yaml.load(f.read(), Loader=yaml.CLoader)
    except Exception as e:
        sys.exit("ERROR: could not read file %s (%s)" % (file_path, e))


def load_json(file_path):
    # Load json file
    if not os.path.exists(file_path):
        sys.exit("ERROR: file %s not found" % file_path)
    try:
        with open(file_path) as f:
            return json.loads(f.read())
    except Exception as e:
        sys.exit("ERROR: could not read file %s (%s)" % (file_path, e))


def build_ansible_vars_file(file_path, configuration):
    c = configuration
    data = dict(
        repo_username=c['repo_username'],
        repo_password=c['repo_password'],
        pg_version=c['pg_version'],
        pg_type=c['pg_type'],
        bdr_dbname=c['bdr_dbname'],
        bdr_writers=c['bdr_writers'],
        bdr_wal_decoder=c['bdr_wal_decoder'],
        postgres_user=c['postgres_user'],
        postgres_group=c['postgres_group'],
        dbt2_warehouse=c['dbt2_warehouse'],
        pg_bin_path=c['pg_bin_path'],
        pg_login_unix_socket='/tmp',
        disable_logging=False,
        pg_unix_socket_directories=['/tmp'],
        pg_database='postgres',
        pg_service='postgres',
    )
    try:
        with open(file_path, 'w') as f:
            f.write(json.dumps(data, indent=2, sort_keys=True))
    except Exception as e:
        sys.exit("ERROR: could not write %s (%s)" % (file_path, e))


def copy_ansible_code(project_dir):
    script_dir = Path(__file__).parent.resolve()
    try:
        shutil.copytree(script_dir / '..' / 'ansible', project_dir / 'ansible')
    except Exception as e:
        sys.exit("ERROR: cannot copy ansible code (%s)" % e)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'project_path',
        metavar='PROJECT_PATH',
        type=Path,
        help="Project path.",
    )
    parser.add_argument(
        'configuration_path',
        metavar='CONFIGURAION_YAML_PATH',
        type=Path,
        help="configuration.yml path.",
    )
    parser.add_argument(
        '--architecture', '-a',
        dest='architecture',
        metavar='BDR_ARCHITECTURE',
        choices=['gold', 'silver'],
        default='silver',
        help="Target BDR architecture. Default: %(default)s"
    )
    env = parser.parse_args()

    servers = load_yaml(env.project_path / 'servers.yml')
    configuration = load_yaml(env.configuration_path)
    vars = load_json(env.project_path / 'terraform_vars.json')
    template(
        'config-%s.yml.j2' % env.architecture,
        env.project_path / 'config.yml',
        dict(
            servers=servers['servers'],
            vars=vars,
            configuration=configuration
        )
    )
    template(
        'inventory-%s.yml.j2' % env.architecture,
        env.project_path / 'inventory.yml',
        dict(servers=servers['servers'])
    )
    template(
        'add_hosts.sh.j2',
        env.project_path / 'add_hosts.sh',
        dict(servers=servers['servers'], vars=vars)
    )
    os.chmod(env.project_path / 'add_hosts.sh', 0o755)
    template(
        'edb-repo-creds.txt.j2',
        env.project_path / 'edb-repo-creds.txt',
        dict(configuration=configuration)
    )
    os.chmod(env.project_path / 'edb-repo-creds.txt', 0o600)
    build_ansible_vars_file(
        env.project_path / 'ansible_vars.json', configuration
    )
    template(
        'deploy.sh.j2',
        env.project_path / 'deploy.sh',
        dict(
            configuration=configuration,
            vars=vars,
            architecture=env.architecture,
        )
    )
    os.chmod(env.project_path / 'deploy.sh', 0o755)
    copy_ansible_code(env.project_path)
