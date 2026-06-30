import hashlib
import os
import shutil
import subprocess


def _cachedSource(url, ref):
	cacheRoot = os.environ.get('V8_PACKAGER_GIT_CACHE')
	if not cacheRoot:
		return url, ref

	repositoryKey = hashlib.sha256(url.encode('utf-8')).hexdigest()
	refKey = hashlib.sha256(ref.encode('utf-8')).hexdigest()
	cacheRepository = os.path.join(cacheRoot, repositoryKey + '.git')
	cacheRef = 'refs/v8-packager/' + refKey
	os.makedirs(cacheRepository, exist_ok=True)
	if not os.path.isfile(os.path.join(cacheRepository, 'HEAD')):
		subprocess.check_call([
			'git', 'init', '--bare', '--quiet',
			'--initial-branch=v8-packager'
		], cwd=cacheRepository)

	print('Cache {}@{} in {}'.format(url, ref, cacheRepository))
	subprocess.check_call([
		'git', 'fetch', '--depth=1', '--force', '--no-tags', url, ref
	], cwd=cacheRepository)
	subprocess.check_call([
		'git', 'update-ref', cacheRef, 'FETCH_HEAD'
	], cwd=cacheRepository)
	return cacheRepository, cacheRef


def fetch(url, target):
	parts = url.split('.git@')
	if len(parts) > 1:
		url = parts[0] + '.git'
		ref = parts[1]
	else:
		# Handle repos without .git suffix (e.g. .../simdutf@hash)
		parts = url.rsplit('@', 1)
		if len(parts) > 1:
			url = parts[0]
			ref = parts[1]
		else:
			ref = 'HEAD'

	target = os.path.abspath(target)
	if not os.path.exists(target):
		os.makedirs(target)

	print('Fetch {}@{} into {}'.format(url, ref, target))
	fetchUrl, fetchRef = _cachedSource(url, ref)

	if not os.path.isdir(os.path.join(target, '.git')):
		subprocess.check_call([
			'git', 'init', '--quiet', '--initial-branch=v8-packager'
		], cwd=target)
	fetch_args = [
		'git', 'fetch', '--depth=1', '--update-shallow', '--update-head-ok',
		'--verbose', fetchUrl, fetchRef
	]
	if subprocess.call(fetch_args, cwd=target) != 0:
		print('RETRY: {}'.format(target))
		shutil.rmtree(target, ignore_errors=True)
		subprocess.check_call([
			'git', 'init', '--quiet', '--initial-branch=v8-packager'
		], cwd=target)
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

def reset(target):
	subprocess.check_call(['git', 'reset', '--hard', 'HEAD'], cwd=target)
