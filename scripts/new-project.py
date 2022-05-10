# coding: utf-8

import argparse
import json
from pathlib import Path, PurePath
import os
import sys
import shutil
import yaml

from jinja2 import Environment, FileSystemLoader

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend


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


def generate_ssh_key_pair(dir):
    key = rsa.generate_private_key(
        backend=default_backend(),
        public_exponent=65537,
        key_size=2048
    )

    b_private_key = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()
    )

    b_public_key = key.public_key().public_bytes(
        serialization.Encoding.OpenSSH,
        serialization.PublicFormat.OpenSSH
    )

    try:
        priv_key_path = dir / "ssh-id_rsa"
        with open(priv_key_path, 'wb') as f:
            f.write(b_private_key)
        os.chmod(priv_key_path, 0o600)
    except Exception as e:
        sys.exit("ERROR: could not write %s (%s)" % (priv_key_path, e))

    try:
        pub_key_path = dir / "ssh-id_rsa.pub"
        with open(pub_key_path, 'wb') as f:
            f.write(b_public_key + b'\n')
    except Exception as e:
        sys.exit("ERROR: could not write %s (%s)" % (pub_key_path, e))

    return (priv_key_path, pub_key_path)


def create_project_dir(dir, csp):
    if os.path.exists(dir):
        sys.exit("ERROR: directory %s already exists" % dir)

    script_dir = Path(__file__).parent.resolve()
    try:
        shutil.copytree(script_dir / '..' / 'terraform' / csp, dir)
    except Exception as e:
        sys.exit("ERROR: cannot create project directory %s (%s)" % (dir, e))


def load_infra_file(file_path):
    # Load AWS infra. data
    if not os.path.exists(file_path):
        sys.exit("ERROR: file %s not found" % file_path)

    try:
        with open(file_path) as f:
            return yaml.load(f.read(), Loader=yaml.CLoader)
    except Exception as e:
        sys.exit("ERROR: could not read file %s (%s)" % (file_path, e))


def to_terraform_vars(dir, filename, vars):
    dest = dir / filename
    try:
        with open(dest, 'w') as f:
            f.write(json.dumps(vars, indent=2, sort_keys=True))
    except Exception as e:
        sys.exit("ERROR: could not write %s (%s)" % (dest, e))


def regions_to_peers(regions):
    region_list = list(regions.keys())
    region_list_cpy = region_list.copy()
    peer_list = []
    i = 0
    for r in region_list:
        for p in range(i+1, len(region_list_cpy)):
            peer_list.append((r, region_list_cpy[p]))
        i += 1
    return peer_list


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'project_path',
        metavar='PROJECT_PATH',
        type=Path,
        help="Project path.",
    )
    parser.add_argument(
        'infra_file',
        metavar='INFRA_FILE_YAML',
        type=Path,
        help="CSP infrastructure (YAML format) file path."
    )
    parser.add_argument(
        '--cloud-service-provider', '-c',
        metavar='CLOUD_SERVICE_PROVIDER',
        dest='csp',
        choices=['aws'],
        default='aws',
        help="Cloud Service Provider. Default: %(default)s"
    )
    env = parser.parse_args()

    # Duplicate terraform code into target project directory
    create_project_dir(env.project_path, env.csp)
    # Load infrastructure variable from the YAML file passed
    infra_vars = load_infra_file(env.infra_file)
    # Generate a new SSH key pair
    (ssh_priv_key, ssh_pub_key) = generate_ssh_key_pair(env.project_path)
    # Inject SSH variables
    infra_vars['ssh_priv_key'] = str(ssh_priv_key.resolve())
    infra_vars['ssh_pub_key'] = str(ssh_pub_key.resolve())
    # Transform infrastructure configuration to terraform variables
    to_terraform_vars(env.project_path, 'terraform_vars.json', infra_vars)

    # Generate main.tf and providers.tf
    template_vars = {}
    template_vars['regions'] = infra_vars['regions'].copy()
    template_vars['peers'] = regions_to_peers(infra_vars['regions'])
    template_vars['machine_regions'] = \
        list({ v['region']: 1 for k, v in infra_vars['machines'].items() }.keys())  # noqa
    template(
        'main.tf.j2', env.project_path / 'main.tf', template_vars
    )
    template(
        'providers.tf.j2', env.project_path / 'providers.tf', template_vars
    )
