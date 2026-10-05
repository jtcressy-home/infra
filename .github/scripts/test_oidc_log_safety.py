import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('argocd-oidc-login.sh')

class LoginOutputTests(unittest.TestCase):
    def test_response_and_claims_never_reach_logs(self):
        for mode in ['failure', 'missing', 'success']:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                curl = Path(tmp) / 'curl'
                curl.write_text('''#!/usr/bin/env python3
import json, os, sys
args=sys.argv[1:]
if '-o' not in args:
 print(json.dumps({'value':'eyJhbGciOiJub25lIn0.eyJwcml2YXRlIjoiUFJJVkFURV9DTEFJTSJ9.signature'}))
else:
 mode=os.environ['MOCK_MODE']
 body={'access_token':'PRIVATE_TOKEN'} if mode=='success' else {'error':'PRIVATE_RESPONSE'}
 open(args[args.index('-o')+1],'w').write(json.dumps(body))
 print('401' if mode=='failure' else '200',end='')
''')
                curl.chmod(0o755)
                env = dict(os.environ, PATH=tmp+':'+os.environ['PATH'], MOCK_MODE=mode,
                           ARGOCD_SERVER='example.invalid', DEX_ISSUER='https://example.invalid',
                           ACTIONS_ID_TOKEN_REQUEST_URL='https://example.invalid?request=1',
                           ACTIONS_ID_TOKEN_REQUEST_TOKEN='synthetic', ACTIONS_STEP_DEBUG='true')
                result = subprocess.run(['bash',str(SCRIPT)],env=env,capture_output=True,text=True)
                self.assertNotIn('PRIVATE_',result.stderr)
                if mode == 'success':
                    self.assertEqual(result.returncode,0)
                    self.assertEqual(result.stdout.strip(),'PRIVATE_TOKEN')
                else:
                    self.assertNotEqual(result.returncode,0)
                    self.assertEqual(result.stdout,'')

if __name__ == '__main__':
    unittest.main()
