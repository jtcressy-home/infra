#!/usr/bin/env python3
"""Validate the rendered phase-one boundary, not merely Helm input values."""
import argparse
import base64
from pathlib import Path
import yaml


def objects(path):
    return [x for x in yaml.safe_load_all(Path(path).read_text()) if x]


def validate(stack, victoria):
    def one(kind, name):
        matches = [x for x in stack if x['kind'] == kind and x['metadata']['name'] == name]
        assert len(matches) == 1, (kind, name, len(matches))
        return matches[0]
    am = one('Alertmanager', 'kps')
    assert am['metadata']['namespace'] == 'kube-system'
    spec = am['spec']
    assert spec['image'] == 'quay.io/prometheus/alertmanager:v0.31.1'
    assert spec['replicas'] == 1
    assert 'alertmanagerConfigSelector' not in spec, 'staging must not import other receivers'
    assert 'alertmanagerConfigNamespaceSelector' not in spec
    claim = spec['storage']['volumeClaimTemplate']['spec']
    assert claim['storageClassName'] == 'local'
    assert claim['accessModes'] == ['ReadWriteOnce']
    assert claim['resources']['requests']['storage'] == '1Gi'
    service = one('Service', 'kps-alertmanager')
    assert service['metadata']['namespace'] == 'kube-system'
    assert service['spec']['type'] == 'ClusterIP'
    assert any(p['port'] == 9093 for p in service['spec']['ports'])
    assert service['spec']['selector']['alertmanager'] == 'kps'
    secret = one('Secret', 'alertmanager-kps')
    config_text = base64.b64decode(secret['data']['alertmanager.yaml']).decode()
    config = yaml.safe_load(config_text)
    assert config['receivers'] == [{'name': 'staging-no-delivery'}], 'outbound activation is separate'
    assert config['route']['receiver'] == 'staging-no-delivery'
    assert not config['route'].get('routes')
    assert not config.get('inhibit_rules')
    vm = [x for x in victoria if x['kind'] == 'VMAlert']
    assert len(vm) == 1
    assert vm[0]['spec']['notifiers'] == [{'url': 'http://kps-alertmanager.kube-system.svc:9093'}]
    assert vm[0]['spec']['evaluationInterval'] == '1m'
    assert vm[0]['spec']['selectAllByDefault'] is True
    return config_text


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stack')
    parser.add_argument('victoria')
    parser.add_argument('--config-output')
    args = parser.parse_args()
    text = validate(objects(args.stack), objects(args.victoria))
    if args.config_output:
        Path(args.config_output).write_text(text)
    print('Alertmanager intake, VMAlert route, local storage and no-delivery boundary passed.')
