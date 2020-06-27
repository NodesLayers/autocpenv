# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function

# Standard library imports
import os
import random
import sys
import tempfile
from string import Template

# Local imports
from . import paths
from .compat import numeric_types, platform, string_types
from .vendor import yaml


def _preprocess_dict(d):
    if platform in d:
        return d[platform]


def _preprocess_seq(seq):
    value = []
    for item in seq:
        item_value = PREPROCESSORS[type(item)](item)
        if isinstance(item_value, (list, tuple, set)):
            value.extend(item_value)
        else:
            value.append(item_value)
    return value


def _preprocess_str(s):
    return str(s)


PREPROCESSORS = {
    dict: _preprocess_dict,
    list: _preprocess_seq,
    set: _preprocess_seq,
    tuple: _preprocess_seq,
}

PREPROCESSORS.update(
    dict((typ, _preprocess_str) for typ in numeric_types + string_types)
)


def preprocess_dict(d):
    '''
    Preprocess a dict to be used as environment variables.

    :param d: dict to be processed
    '''

    out_env = {}
    for k, v in d.items():

        if not type(v) in PREPROCESSORS:
            raise KeyError('Invalid type in dict: {}'.format(type(v)))

        out_env[k] = PREPROCESSORS[type(v)](v)

    return out_env


def _join_dict(d, k, v):
    '''Add a dict value to an env dict.

    Assumes that a dict value contains system platform keys (win, mac, linux).
    If a key is missing - we do not add this key to the result dict.
    '''

    if platform in v:
        d[k] = v[platform]


def _join_str(d, k, v):
    '''Add a string value to env dict'''

    d[k] = str(v)


def _join_seq(d, k, v):
    '''Add a sequence value to env dict'''

    if k not in d:
        d[k] = list(v)

    elif isinstance(d[k], list):
        for item in v:
            if item not in d[k]:
                d[k].insert(0, item)

    elif isinstance(d[k], string_types):
        v.append(d[k])
        d[k] = v


JOINERS = {
    dict: _join_dict,
    list: _join_seq,
    set: _join_seq,
    tuple: _join_seq,
}

JOINERS.update(
    dict((typ, _join_str) for typ in numeric_types + string_types)
)


def join_dicts(*dicts):
    '''Join a bunch of dicts'''

    out_dict = {}

    for d in dicts:

        for k, v in d.items():

            if type(v) not in JOINERS:
                raise KeyError('Invalid type in dict: {}'.format(type(v)))

            JOINERS[type(v)](out_dict, k, v)

    return out_dict


def env_to_dict(env, pathsep=os.pathsep):
    '''
    Convert a dict containing environment variables into a standard dict.
    Variables containing multiple values will be split into a list based on
    the argument passed to pathsep.

    :param env: Environment dict like dict(os.environ)
    :param pathsep: Path separator used to split variables
    '''

    out_dict = {}

    for k, v in env.items():
        if pathsep in v:
            out_dict[k] = v.split(pathsep)
        else:
            out_dict[k] = v

    return out_dict


def dict_to_env(d, pathsep=os.pathsep):
    '''
    Convert a python dict to a dict containing valid environment variable
    values.

    :param d: Dict to convert to an env dict
    :param pathsep: Path separator used to join lists(default os.pathsep)
    '''

    out_env = {}

    for k, v in d.items():
        if isinstance(v, list):
            out_env[k] = pathsep.join(v)
        elif isinstance(v, string_types):
            out_env[k] = v
        else:
            raise TypeError('{} not a valid env var type'.format(type(v)))

    return out_env


def expand_envvars(env):
    '''
    Expand all environment variables in an environment dict

    :param env: Environment dict
    '''

    out_env = {}

    for k, v in env.items():
        out_env[k] = Template(v).safe_substitute(env)

    # Expand twice to make sure we expand everything we possibly can
    for k, v in out_env.items():
        out_env[k] = Template(v).safe_substitute(out_env)

    return out_env


def get_store_env_tmp():
    '''Returns an unused random filepath.'''

    tempdir = tempfile.gettempdir()
    temp_name = 'envstore{0:0>3d}'
    temp_path = paths.normalize(
        tempdir,
        temp_name.format(random.getrandbits(9))
    )
    if not os.path.exists(temp_path):
        return temp_path
    else:
        return get_store_env_tmp()


def store_env(path=None):
    '''Encode current environment as yaml and store in path or a temporary
    file. Return the path to the stored environment.
    '''

    path = path or get_store_env_tmp()

    env_dict = yaml.safe_dump(dict(os.environ), default_flow_style=False)

    with open(path, 'w') as f:
        f.write(env_dict)

    return path


def restore_env(env_dict):
    '''Set environment variables in the current python process from a dict
    containing envvars and values.'''

    if hasattr(sys, 'real_prefix'):
        sys.prefix = sys.real_prefix
        del(sys.real_prefix)

    replace_osenviron(expand_envvars(dict_to_env(env_dict)))


def restore_env_from_file(env_file):
    '''Restore the current environment from an environment stored in a yaml
    yaml file.

    :param env_file: Path to environment yaml file.
    '''

    with open(env_file, 'r') as f:
        env_dict = yaml.safe_load(f.read())

    restore_env(env_dict)


def set_env(*env_dicts):
    '''Set environment variables in the current python process from a dict
    containing envvars and values.'''

    old_env_dict = env_to_dict(dict(os.environ))
    new_env_dict = join_dicts(old_env_dict, *env_dicts)
    new_env = dict_to_env(new_env_dict)
    replace_osenviron(expand_envvars(new_env))


def set_env_from_file(env_file):
    '''Restore the current environment from an environment stored in a yaml
    yaml file.

    :param env_file: Path to environment yaml file.
    '''

    with open(env_file, 'r') as f:
        env_dict = yaml.safe_load(f.read())

    if 'environment' in env_dict:
        env_dict = env_dict['environment']

    set_env(env_dict)


def replace_osenviron(env_dict):
    for k in os.environ.keys():
        if k not in env_dict:
            del os.environ[k]

    for k, v in env_dict.items():
        os.environ[k] = v