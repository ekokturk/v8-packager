import hashlib
import os
import shutil
import subprocess


def _fetch(args, cwd):
	env = os.environ.copy()
	env['GIT_TERMINAL_PROMPT'] = '0'
	command = [
		'git', '-c', 'http.lowSpeedLimit=1000',
		'-c', 'http.lowSpeedTime=120',
		args[0], '--progress', *args[1:],
	]
	try:
		subprocess.check_call(command, cwd=cwd, env=env, timeout=1800)
	except subprocess.TimeoutExpired as error:
		raise RuntimeError(
			f"Git fetch timed out after 30 minutes in '{cwd}': {' '.join(command)}"
		) from error


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

	print('Cache {}@{} in {}'.format(url, ref, cacheRepository), flush=True)
	_fetch(['fetch', '--depth=1', '--force', '--no-tags', url, ref], cacheRepository)
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

	print('Fetch {}@{} into {}'.format(url, ref, target), flush=True)
	fetchUrl, fetchRef = _cachedSource(url, ref)

	if not os.path.isdir(os.path.join(target, '.git')):
		subprocess.check_call([
			'git', 'init', '--quiet', '--initial-branch=v8-packager'
		], cwd=target)
	fetch_args = [
		'fetch', '--depth=1', '--update-shallow', '--update-head-ok',
		'--verbose', fetchUrl, fetchRef
	]
	try:
		_fetch(fetch_args, target)
	except subprocess.CalledProcessError:
		print('RETRY: {}'.format(target))
		shutil.rmtree(target, ignore_errors=True)
		subprocess.check_call([
			'git', 'init', '--quiet', '--initial-branch=v8-packager'
		], cwd=target)
		_fetch(fetch_args, target)
	subprocess.check_call(['git', 'checkout', '-f', '-B', 'Branch_'+ref, 'FETCH_HEAD'], cwd=target)

def applyPatch(patchFile, target):
	check = subprocess.run(
		['git', 'apply', '--ignore-space-change', '--check', patchFile],
		cwd=target,
		capture_output=True,
		text=True,
	)
	if check.returncode == 0:
		subprocess.check_call(
			['git', 'apply', '--ignore-space-change', patchFile],
			cwd=target,
		)
		print(f"Patch '{patchFile}' applied successfully.")
		return

	reverseCheck = subprocess.run(
		[
			'git', 'apply', '--ignore-space-change', '--reverse', '--check',
			patchFile,
		],
		cwd=target,
		capture_output=True,
		text=True,
	)
	if reverseCheck.returncode == 0:
		print(f"Patch '{patchFile}' has already been applied.")
		return

	error = (check.stderr or check.stdout).strip()
	if not error:
		error = (reverseCheck.stderr or reverseCheck.stdout).strip()
	raise RuntimeError(
		f"Failed to apply patch '{patchFile}' in '{target}':"
		+ (f"\n{error}" if error else " unknown git apply error")
	)

def reset(target):
	subprocess.check_call(['git', 'reset', '--hard', 'HEAD'], cwd=target)
