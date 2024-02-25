import os
import shutil
import subprocess

def fetch(url, target):
	parts = url.split('.git@')
	if len(parts) > 1:
		url = parts[0] + '.git'
		ref = parts[1]
	else:
		ref = 'HEAD'

	target = os.path.abspath(target)
	if not os.path.exists(target):
		os.makedirs(target)

	print('Fetch {}@{} into {}'.format(url, ref, target))

	if not os.path.isdir(os.path.join(target, '.git')):
		subprocess.check_call(['git', 'init'], cwd=target)
	fetch_args = ['git', 'fetch', '--depth=1', '--update-shallow', '--update-head-ok', '--verbose', url, ref]
	if subprocess.call(fetch_args, cwd=target) != 0:
		print('RETRY: {}'.format(target))
		shutil.rmtree(target, ignore_errors=True)
		subprocess.check_call(['git', 'init'], cwd=target)
		subprocess.check_call(fetch_args, cwd=target)
	subprocess.check_call(['git', 'checkout', '-f', '-B', 'Branch_'+ref, 'FETCH_HEAD'], cwd=target)

def applyPatch(patchFile, target):
	with open(os.devnull, 'w') as devnull:
		try:
			subprocess.check_call(['git', 'apply', '--check', patchFile], cwd=target, stdout=devnull, stderr=devnull)
		except subprocess.CalledProcessError:
			print(f"Patch '{patchFile}' has already been applied.")
		else:
			subprocess.call(['git', 'apply', patchFile], cwd=target)
			print(f"Patch '{patchFile}' applied successfully.")