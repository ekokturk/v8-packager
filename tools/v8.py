
import io
import os
import re
import shutil
import stat
import subprocess
import sys
import zipfile
import requests
import platform as sysPlatform
from enum import Enum
from typing import List

import tools.git as git
from tools.types import ArchType, EnvVars, PlatformType, BuildConfig

class V8:
	class LibraryType(Enum):
		Shared = "Shared"
		Static = "Static"

	class Version:
		def __init__(self, major: int, minor: int, build: int = None, patch: int = None):
			self.major = major
			self.minor = minor
			self.build = build
			self.patch = patch

		@staticmethod
		def fromString(versionStr: str) -> 'V8.Version':
			v = versionStr.split('.')
			major, minor, build, patch = None, None, None, None
			if len(v) >= 1:
				major = int(v[0])
			if len(v) >= 2:
				minor = int(v[1])
			if len(v) >= 3:
				build = int(v[2])
			if len(v) >= 4:
				patch = int(v[3])
			return V8.Version(major, minor, build, patch)
		
		def toString(self):
			components = [str(comp) for comp in (self.major, self.minor, self.build, self.patch) if comp is not None]
			return ".".join(components)


	class BuildSettings:
		def __init__(self, platform: PlatformType, arch: ArchType, config: BuildConfig):
			self.platform = platform
			self.arch = arch
			self.config = config

	class ProjectSettings:
		def __init__(self, libraryType: 'V8.LibraryType' = None):
			self.libraryType: 'V8.LibraryType' = libraryType if libraryType is not None else V8.LibraryType.Static
			self.defaultArgs = self._getDefaultArgs()
			pass

		def _getDefaultArgs(self):
			args = dict()
			# General
			args['use_custom_libcxx'] = False
			args['use_custom_libcxx_for_host'] = True
			args['is_component_build'] = self.libraryType == V8.LibraryType.Shared 
			args['v8_static_library'] = self.libraryType == V8.LibraryType.Static
			args['v8_monolithic'] = self.libraryType == V8.LibraryType.Static

			# Validation/Debugging
			args['treat_warnings_as_errors'] = False
			args['fatal_linker_warnings'] = False
			args['v8_optimized_debug'] = True

			# Extensions
			args['v8_use_snapshot'] = True
			args['v8_use_external_startup_data'] = False
			args['v8_enable_verify_heap'] = False
			args['v8_enable_fast_mksnapshot'] = False
			args['v8_enable_fast_torque'] = False
			args['v8_enable_pointer_compression'] = True
			args['v8_enable_i18n_support'] = False
			args['v8_enable_webassembly'] = False
			args['enable_rust'] = False
			args['v8_enable_fuzztest'] = False

			return args

		def getBuildArgs(self, buildSettings: 'V8.BuildSettings'):
			args = self.defaultArgs.copy()

			# Platform
			args['is_clang'] = True  # V8 13.x requires Clang on all platforms (clang-cl on Windows)

			if PlatformType.Windows == buildSettings.platform:
				args['target_os'] = "win"
			elif PlatformType.Linux == buildSettings.platform:
				args['target_os'] = "linux"
				args['use_sysroot'] = False
				if self.libraryType == V8.LibraryType.Static:
					args['v8_tls_used_in_library'] = True
			elif PlatformType.Android == buildSettings.platform:
				args['target_os'] = "android"
			else:
				raise RuntimeError("Error: Unsupported Platform")

			if ArchType.x64 == buildSettings.arch:
				args['target_cpu'] = "x64"
			elif ArchType.Arm64 == buildSettings.arch:
				args['target_cpu'] = "arm64"
			else:
				raise RuntimeError("Error: Unsupported CPU architecture")

			# Validation/Debugging
			args['is_debug'] = buildSettings.config == BuildConfig.Debug
			if buildSettings.config == BuildConfig.Debug:
				args['symbol_level'] = 1
			else:
				args['symbol_level'] = 0

			return args
		
		def getCompileDefinitions(self, buildSettings: 'V8.BuildSettings') -> List[str]:
			defs = set()
			if self.defaultArgs.get('v8_enable_pointer_compression') is True:
				defs.add('V8_ENABLE_SANDBOX=1')
				defs.add('V8_COMPRESS_POINTERS=1')
				defs.add('V8_31BIT_SMIS_ON_64BIT_ARCH=1')

			if self.defaultArgs.get('v8_enable_31bit_smis_on_64bit_arch') is True:
				defs.add('V8_ENABLE_SANDBOX=1')
				defs.add('V8_31BIT_SMIS_ON_64BIT_ARCH=1')

			buildArgs = self.getBuildArgs(buildSettings)
			isDebug = buildArgs.get('is_debug', False)
			debuggingFeatures = buildArgs.get('v8_enable_debugging_features', isDebug)
			dcheckAlwaysOn = buildArgs.get('v8_dcheck_always_on', False)
			v8Checks = buildArgs.get('v8_enable_v8_checks', debuggingFeatures)
			memoryAccountingChecks = buildArgs.get(
				'v8_enable_memory_accounting_checks',
				debuggingFeatures or dcheckAlwaysOn,
			)
			cppgcApiChecks = buildArgs.get(
				'cppgc_enable_api_checks',
				isDebug or dcheckAlwaysOn,
			)

			if v8Checks:
				defs.add('V8_ENABLE_CHECKS')
			if memoryAccountingChecks:
				defs.add('V8_ENABLE_MEMORY_ACCOUNTING_CHECKS')
			if cppgcApiChecks:
				defs.add('CPPGC_ENABLE_API_CHECKS')

			return sorted(defs)
		
	@staticmethod
	def initializeRepository(version: 'V8.Version'):
		git.fetch('https://chromium.googlesource.com/v8/v8.git@' + f'{version.major}.{version.minor}-lkgr' , 'v8')
		return V8(os.getcwd())

	def __init__(self, root):
		self._v8Dir = os.path.abspath(os.path.join(root, 'v8'))
		if not os.path.exists(self._v8Dir):
			raise RuntimeError("Error: Expected V8 project to have been initialized")

		self._binDir = os.path.abspath(os.path.join(root, 'bin'))
		self._patchDir = os.path.abspath(os.path.join(root, 'patches'))

		versionContent = open(os.path.join(self._v8Dir, 'include/v8-version.h')).read()
		self.version = V8.Version(
			int(re.search(r'V8_MAJOR_VERSION (\d+)', versionContent).group(1)),
			int(re.search(r'V8_MINOR_VERSION (\d+)', versionContent).group(1)),
			int(re.search(r'V8_BUILD_NUMBER (\d+)', versionContent).group(1)),
			int(re.search(r'V8_PATCH_LEVEL (\d+)', versionContent).group(1))
		)
	
	def fetchBinaryDependencies(self, platforms: List[PlatformType] = None):
		platforms = set(platforms or list(PlatformType))

		def _ensureExecutable(path):
			if sysPlatform.system() != 'Windows':
				mode = os.stat(path).st_mode
				os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

		def _downloadBinaryFile(file, url, out):
			outputFile = os.path.join(out, file)
			if os.path.exists(outputFile):
				_ensureExecutable(outputFile)
				return
			response = requests.get(url)
			response.raise_for_status()
			zip_file = zipfile.ZipFile(io.BytesIO(response.content))
			os.makedirs(out, exist_ok=True)
			zip_file.extract(file, out)
			_ensureExecutable(outputFile)
			print(f"Downloaded '{file}'")

		def _downloadVersionedBinaryFile(file, url, version, out):
			stampFile = os.path.join(out, file + '.version')
			outputFile = os.path.join(out, file)
			if os.path.exists(stampFile) and os.path.exists(outputFile):
				with open(stampFile) as f:
					if f.read().strip() == version:
						_ensureExecutable(outputFile)
						return
			response = requests.get(url)
			response.raise_for_status()
			zip_file = zipfile.ZipFile(io.BytesIO(response.content))
			os.makedirs(out, exist_ok=True)
			zip_file.extract(file, out)
			_ensureExecutable(outputFile)
			with open(stampFile, 'w') as f:
				f.write(version)
			print(f"Downloaded '{file}'")

		# Read the GN version required by this V8 checkout from DEPS
		namespace = {}
		with open(os.path.join(self._v8Dir, 'DEPS')) as f:
			exec('Var = lambda name: vars[name]; Str = str', namespace)
			exec(f.read(), namespace)
		gnVersion = namespace.get('vars', {}).get('gn_version', 'latest')

		# We need prebuilt gn and ninja to compile the project
		ninjaUrl = "https://github.com/ninja-build/ninja/releases/download/v1.13.2/ninja-{}.zip"
		gnUrl = "https://chrome-infra-packages.appspot.com/dl/gn/gn/{}-amd64/+/" + gnVersion
		if PlatformType.Linux in platforms or PlatformType.Android in platforms:
			_downloadBinaryFile('ninja', ninjaUrl.format('linux'), self._binDir)
			_downloadVersionedBinaryFile('gn', gnUrl.format('linux'), gnVersion, self._binDir)
		if PlatformType.Windows in platforms:
			_downloadBinaryFile('ninja.exe', ninjaUrl.format('win'), self._binDir)
			_downloadVersionedBinaryFile('gn.exe', gnUrl.format('windows'), gnVersion, self._binDir)

	def fetchProjectDependencies(self, platforms: List[PlatformType] = None):
		platforms = set(platforms or list(PlatformType))
		requiredDeps = [
			'v8/build',
			'v8/buildtools',
			'v8/base/trace_event/common',
			'v8/third_party/abseil-cpp',
			'v8/third_party/fast_float/src',
			'v8/third_party/fp16/src',
			'v8/third_party/highway/src',
			'v8/third_party/icu',
			'v8/third_party/jinja2',
			'v8/third_party/libc++/src',
			'v8/third_party/libc++abi/src',
			'v8/third_party/libunwind/src',
			'v8/third_party/llvm-libc/src',
			'v8/third_party/markupsafe',
			'v8/third_party/googletest/src',
			'v8/third_party/partition_alloc',
			'v8/third_party/perfetto',
			'v8/third_party/simdutf',
			'v8/third_party/zlib',
			'v8/tools/clang',
			'v8/third_party/depot_tools',
		]
		if PlatformType.Android in platforms:
			requiredDeps.extend([
				'v8/third_party/android_platform',
				'v8/third_party/catapult',
				'v8/third_party/colorama/src',
				'v8/third_party/cpu_features/src',
			])
		namespace = {}
		with open(os.path.join(self._v8Dir, 'DEPS')) as file:
			exec('Var = lambda name: vars[name]; Str = str', namespace)
			exec(file.read(), namespace)
		deps = namespace.get('deps')
		for name, url in deps.items():
			if not name.startswith('v8'):
				name = 'v8/' + name
			if name in requiredDeps:
				if(isinstance(url, dict)):
					git.fetch(url["url"], name)
				else:
					git.fetch(url, name)

		if PlatformType.Android in platforms:
			self.fetchAndroidToolchain()

		gclientArgsFile = os.path.join(self._v8Dir, 'build/config/gclient_args.gni')
		if not os.path.isfile(gclientArgsFile) and os.path.exists(os.path.dirname(gclientArgsFile)):
			with open(gclientArgsFile, 'a') as f:
				f.write('declare_args() { checkout_google_benchmark = false }\n')

		# Download prebuilt clang toolchain (normally done by gclient sync hook)
		# Required for is_clang=true; update.py is self-contained and uses its own stamp file.
		clangUpdateScript = os.path.join(self._v8Dir, 'tools', 'clang', 'scripts', 'update.py')
		clangStampFile = os.path.join(self._v8Dir, 'third_party', 'llvm-build', 'Release+Asserts', 'cr_build_revision')
		if os.path.exists(clangUpdateScript) and not os.path.exists(clangStampFile):
			print("Downloading prebuilt clang toolchain (this may take a while)...")
			subprocess.check_call([sys.executable, clangUpdateScript])

	def fetchAndroidToolchain(self):
		namespace = {}
		with open(os.path.join(self._v8Dir, 'DEPS')) as file:
			exec('Var = lambda name: vars[name]; Str = str', namespace)
			exec(file.read(), namespace)
		dependency = namespace['deps']['third_party/android_toolchain/ndk']
		package = dependency['packages'][0]
		version = package['version']
		toolchainDir = os.path.join(self._v8Dir, 'third_party', 'android_toolchain', 'ndk')
		stampFile = os.path.join(toolchainDir, '.cipd-version')
		if os.path.isfile(stampFile):
			with open(stampFile) as file:
				if file.read().strip() == version:
					return

		url = (
			'https://chrome-infra-packages.appspot.com/dl/'
			f"{package['package']}/+/{version}"
		)
		archiveFile = os.path.join(self._v8Dir, 'third_party', 'android_toolchain.zip')
		print('Downloading Android NDK toolchain (this may take a while)...')
		response = requests.get(url, stream=True)
		response.raise_for_status()
		with open(archiveFile, 'wb') as archive:
			for chunk in response.iter_content(chunk_size=1024 * 1024):
				archive.write(chunk)
		if os.path.isdir(toolchainDir):
			shutil.rmtree(toolchainDir)
		os.makedirs(toolchainDir, exist_ok=True)
		with zipfile.ZipFile(archiveFile) as archive:
			archive.extractall(toolchainDir)
		os.remove(archiveFile)
		with open(stampFile, 'w') as file:
			file.write(version)

	def resetRepository(self):
		git.reset(self._v8Dir)
		buildDir = os.path.join(self._v8Dir, 'build')
		if os.path.isdir(os.path.join(buildDir, '.git')):
			git.reset(buildDir)
		outDir = os.path.join(self._v8Dir, 'out.gn')
		if os.path.isdir(outDir):
			print(f"Removing generated build outputs from '{outDir}'")
			shutil.rmtree(outDir)

	def applyPatches(self):
		print('Applying patches')

		# Apply available patch files for the current version.
		# Patch files placed in a subdirectory are applied to the matching
		# sub-repo inside v8/. For example:
		#   patches/13/build/foo.patch  -> applied to v8/build
		#   patches/13/foo.patch        -> applied to v8
		patchDirs = [
			os.path.join(self._patchDir, f'{self.version.major}'), 
	    	os.path.join(self._patchDir, f'{self.version.major}.{self.version.minor}')
		]
		for patchDir in patchDirs:
			for root, _, files in os.walk(patchDir):
				for file in files:
					if file.endswith('.patch'):
						file_path = os.path.join(root, file)
						relPath = os.path.relpath(root, patchDir)
						targetRepo = 'v8' if relPath == '.' else os.path.join('v8', relPath)
						git.applyPatch(os.path.abspath(file_path), targetRepo)

	def _getPatchFiles(self):
		patchFiles = []
		patchDirs = [
			os.path.join(self._patchDir, f'{self.version.major}'),
			os.path.join(self._patchDir, f'{self.version.major}.{self.version.minor}')
		]
		for patchDir in patchDirs:
			if not os.path.isdir(patchDir):
				continue
			for root, _, files in os.walk(patchDir):
				for file in files:
					if file.endswith('.patch'):
						patchFiles.append(os.path.relpath(os.path.join(root, file), self._patchDir))
		return sorted(patchFiles)


	def build(self, outDir: str, projectSettings: ProjectSettings, buildSettingsList: List[BuildSettings]):
		outDir = os.path.abspath(outDir)
		buildSet = set()
		buildInfo = dict()
		for buildSettings in buildSettingsList:
			buildOutDir = os.path.join(outDir, os.path.join(buildSettings.platform.value, buildSettings.arch.value).lower())

			# Compile and export libraries
			result = False
			libOutDir = os.path.join(buildOutDir, 'libs', buildSettings.config.value.lower())
			if buildSettings.platform == PlatformType.Windows:
				result = self._buildWindows(libOutDir, projectSettings, buildSettings)
			if buildSettings.platform == PlatformType.Linux:
				result = self._buildLinux(libOutDir, projectSettings, buildSettings)
			if buildSettings.platform == PlatformType.Android:
				result = self._buildAndroid(libOutDir, projectSettings, buildSettings)

			# Copy static dependencies for each platform/arch
			if result and not (buildSettings.platform, buildSettings.arch) in buildSet:
				os.makedirs(buildOutDir, exist_ok=True)
				with open(os.path.join(buildOutDir, 'v8-version.txt'), 'w') as file:
					file.write(self.version.toString())
				self.exportLicense(buildOutDir)
				self.exportIncludes(os.path.join(buildOutDir, "include"))
				buildSet.add((buildSettings.platform, buildSettings.arch))
			if result:
				self.exportCompileDefinitions(libOutDir, projectSettings, buildSettings)
				key = (buildOutDir, buildSettings.platform, buildSettings.arch)
				buildInfo.setdefault(key, []).append(buildSettings.config)

		for (buildOutDir, platform, arch), configs in buildInfo.items():
			self.exportBuildInfo(buildOutDir, projectSettings, platform, arch, configs)

	def archive(self, archiveDir: str, buildDir: str):
		os.makedirs(archiveDir, exist_ok=True)
		print(f"Archiving libraries in '{archiveDir}'")
		for platformDir in os.listdir(buildDir):
			platformPath = os.path.join(buildDir, platformDir)
			if os.path.isdir(platformPath):
				for archDir in os.listdir(platformPath):
					archPath = os.path.join(platformPath, archDir)
					archiveFile = f"{platformDir}-{archDir}.zip"
					with zipfile.ZipFile(
						os.path.join(archiveDir, archiveFile),
						'w',
						compression=zipfile.ZIP_DEFLATED,
						compresslevel=6,
					) as archive:
						for root, dirs, files in os.walk(archPath):
							for file in files:
								file_path = os.path.join(root, file)
								archive.write(file_path, arcname=os.path.relpath(file_path, buildDir))

	def exportIncludes(self, outIncludeDir):
		v8IncludeDir = os.path.join(self._v8Dir, 'include')
		if os.path.isdir(outIncludeDir):
			shutil.rmtree(outIncludeDir)
		for root, _, files in os.walk(v8IncludeDir):
			for file in files:
				if file.endswith('.h'):
					relativePath = os.path.relpath(root, v8IncludeDir)
					sourceFile = os.path.join(root, file)
					targetFile = os.path.join(outIncludeDir, relativePath, file)
					os.makedirs(os.path.dirname(targetFile), exist_ok=True)
					shutil.copy(sourceFile, targetFile)

	def exportLicense(self, outDir: str):
		licenseFile = os.path.join(self._v8Dir, 'LICENSE')
		if not os.path.isfile(licenseFile):
			raise RuntimeError(f"Error: Expected V8 license file at {licenseFile}")
		shutil.copy(licenseFile, os.path.join(outDir, 'LICENSE'))

	def exportBuildInfo(
		self,
		outDir: str,
		projectSettings: ProjectSettings,
		platform: PlatformType,
		arch: ArchType,
		configs: List[BuildConfig],
	):
		def _readText(path: str):
			if os.path.isfile(path):
				with open(path, encoding='utf-8', errors='replace') as file:
					return file.read().strip()
			return None

		def _yesNo(value):
			return 'yes' if value else 'no'

		def _enabled(value):
			return 'enabled' if value else 'disabled'

		def _readProperties(path: str):
			properties = dict()
			if os.path.isfile(path):
				with open(path, encoding='utf-8', errors='replace') as file:
					for line in file:
						key, separator, value = line.partition('=')
						if separator:
							properties[key.strip()] = value.strip()
			return properties

		def _getClangVersion(platform: PlatformType):
			compilerName = 'clang-cl.exe' if platform == PlatformType.Windows else 'clang'
			compiler = os.path.join(
				self._v8Dir,
				'third_party',
				'llvm-build',
				'Release+Asserts',
				'bin',
				compilerName,
			)
			if not os.path.isfile(compiler):
				return None

			try:
				output = subprocess.check_output(
					[compiler, '--version'],
					text=True,
					stderr=subprocess.STDOUT,
				)
				firstLine = output.splitlines()[0].strip()
				match = re.search(r'clang version (\d+(?:\.\d+)+)', firstLine)
				return match.group(1) if match else firstLine
			except Exception:
				return None

		def _getGnVersion(platform: PlatformType):
			def _cleanVersion(version):
				prefix = 'git_revision:'
				return version[len(prefix):] if version.startswith(prefix) else version

			gnName = 'gn.exe' if platform == PlatformType.Windows else 'gn'
			version = _readText(os.path.join(self._binDir, gnName + '.version'))
			if version:
				return _cleanVersion(version)

			version = _readText(os.path.join(self._binDir, 'gn.version'))
			if version:
				return _cleanVersion(version)

			gn = os.path.join(self._binDir, gnName)
			if not os.path.isfile(gn):
				return None

			try:
				output = subprocess.check_output(
					[gn, '--version'],
					text=True,
					stderr=subprocess.STDOUT,
				)
				return _cleanVersion(output.splitlines()[0].strip())
			except Exception:
				return None

		clangRevision = _readText(os.path.join(
			self._v8Dir,
			'third_party',
			'llvm-build',
			'Release+Asserts',
			'cr_build_revision',
		))
		gnVersion = _getGnVersion(platform)
		androidNdkProperties = _readProperties(os.path.join(
			self._v8Dir,
			'third_party',
			'android_toolchain',
			'ndk',
			'source.properties',
		))
		androidNdkRevision = androidNdkProperties.get('Pkg.Revision')
		clangVersion = _getClangVersion(platform)
		releaseArgs = projectSettings.getBuildArgs(V8.BuildSettings(platform, arch, BuildConfig.Release))
		debugArgs = projectSettings.getBuildArgs(V8.BuildSettings(platform, arch, BuildConfig.Debug))

		lines = [
			'V8 Package Information',
			'======================',
			f'V8 version: {self.version.toString()}',
			f'Platform: {platform.value}',
			f'Architecture: {arch.value}',
			f'Library type: {projectSettings.libraryType.value}',
			f'Included configurations: {", ".join(config.value for config in configs)}',
			'',
			'Build settings',
			'--------------',
			f'JIT: {_enabled(not releaseArgs.get("v8_jitless", False))}',
			f'Snapshots: {_enabled(releaseArgs.get("v8_use_snapshot", False))}',
			f'External startup data: {_enabled(releaseArgs.get("v8_use_external_startup_data", False))}',
			f'Pointer compression: {_enabled(releaseArgs.get("v8_enable_pointer_compression", False))}',
			f'Internationalization/i18n: {_enabled(releaseArgs.get("v8_enable_i18n_support", False))}',
			f'WebAssembly: {_enabled(releaseArgs.get("v8_enable_webassembly", False))}',
			f'Component/shared build: {_yesNo(releaseArgs.get("is_component_build", False))}',
			f'Static monolithic V8 archive: {_yesNo(releaseArgs.get("v8_monolithic", False))}',
			f'Debug symbols: Debug symbol_level={debugArgs.get("symbol_level", "unknown")}, Release symbol_level={releaseArgs.get("symbol_level", "unknown")}',
			'',
			'Toolchain',
			'---------',
			f'Compiler: {"clang-cl" if platform == PlatformType.Windows else "clang"}',
			f'Clang version: {clangVersion or "unknown"}',
			f'Chromium Clang revision: {clangRevision or "unknown"}',
			f'GN version: {gnVersion or "unknown"}',
			'Ninja version: 1.13.2',
		]

		if platform == PlatformType.Windows:
			lines.extend([
				'C/C++ runtime: dynamic MSVC CRT (/MDd for Debug, /MD for Release)',
				'MSVC iterator debug level: Debug=2, Release=0',
			])
		elif platform == PlatformType.Linux:
			lines.extend([
				'C++ standard library: system libstdc++',
				'Linux sysroot: disabled; uses container system libraries',
				f'Shared-library-safe static TLS: {_yesNo(releaseArgs.get("v8_tls_used_in_library", False))}',
			])
		elif platform == PlatformType.Android:
			lines.extend([
				'C++ standard library: Android NDK libc++',
				f'Android NDK revision: {androidNdkRevision or "unknown"}',
			])

		with open(os.path.join(outDir, 'info.txt'), 'w', encoding='utf-8') as file:
			file.write('\n'.join(lines) + '\n')

	def exportCompileDefinitions(self, definitionsDir: str, projectSettings: ProjectSettings, buildSettings: BuildSettings):
		os.makedirs(definitionsDir, exist_ok=True)
		defs = projectSettings.getCompileDefinitions(buildSettings)
		releaseFile = os.path.join(definitionsDir, 'definitions.txt')
		with open(releaseFile, 'w') as file:
			file.write(';'.join(defs))

	def _buildWindows(self, outLibDir: str, projectSettings: ProjectSettings, buildSettings: BuildSettings):
		if sysPlatform.system() != "Windows":
			print(f'Skipping Windows build, not supported on {sysPlatform.system()}')
			return False
		if ArchType.Arm64 == buildSettings.arch:
			print(f'Skipping Windows build for Arm64, not supported.')
			return False

		print(f'Building V8 v{self.version.toString()} for Windows {buildSettings.arch.value}:')

		env = self._setupWindowsEnv()
		self._compileAndExport(outLibDir, projectSettings, buildSettings, env)
		return True

	def _buildLinux(self, outLibDir: str, projectSettings: ProjectSettings, buildSettings: BuildSettings):
		if sysPlatform.system() != "Linux":
			print(f'Skipping Linux build, not supported on {sysPlatform.system()}')
			return False
		if ArchType.Arm64 == buildSettings.arch:
			print(f'Skipping Linux build for Arm64, not supported.')
			return False
		print(f'Building V8 v{self.version.toString()} for Linux {buildSettings.arch.value}:')

		env = self._setupLinuxEnv(buildSettings.arch)
		self._compileAndExport(outLibDir, projectSettings, buildSettings, env)
		return True

	def _buildAndroid(self, outLibDir: str, projectSettings: ProjectSettings, buildSettings: BuildSettings):
		if sysPlatform.system() != "Linux":
			print(f'Skipping Android build, not supported on {sysPlatform.system()}')
			return False
		print(f'Building V8 v{self.version.toString()} for Android {buildSettings.arch.value}:')

		self.fetchAndroidToolchain()
		env = self._setupAndroidEnv()
		self._compileAndExport(outLibDir, projectSettings, buildSettings, env)
		return True

	def _compileAndExport(self, outLibDir: str, projectSettings: ProjectSettings, buildSettings: BuildSettings, env):
		projectPath = os.path.join(self._v8Dir,'out.gn', buildSettings.platform.value.lower(), buildSettings.arch.value.lower(), buildSettings.config.value.lower())
		self._generateProject(projectPath, projectSettings.getBuildArgs(buildSettings), env)
		target = 'v8_monolith' if projectSettings.libraryType == V8.LibraryType.Static else 'v8'
		self._compileProject(projectPath, target, env)
		self._exportLibs(projectPath, outLibDir, buildSettings.platform, buildSettings.config, projectSettings.libraryType)

	def _exportLibs(self, projectLibDir: str, outLibDir: str, platform: PlatformType, buildConfig: BuildConfig, libraryType: 'V8.LibraryType' = None):
		# Generate pattern to search library
		def _getExpectedOutputFilePatterns(platform: PlatformType, buildConfig: BuildConfig):
			def _generateLibPatterns(libNames: List[str], extensions: List[str]):
				patterns = []
				for libName in libNames:
					escapedBaseName = re.escape(libName)
					escapedExtensions = "|".join(map(re.escape, extensions))
					pattern = rf'^{escapedBaseName}(?:\.(?:{escapedExtensions}))+(\.(?:{escapedExtensions}))?$'
					patterns.append(pattern)
				return patterns

			if libraryType == V8.LibraryType.Static:
				if PlatformType.Windows == platform:
					return [r'^v8_monolith\.lib$']
				else:
					return [r'^libv8_monolith\.a$']

			# Shared library build
			libNames = []
			extensions = []
			if PlatformType.Windows == platform:
				libNames = ["v8", "v8_libbase", "v8_libplatform", "zlib"]
				extensions = ['dll', 'dll.lib']
			else:
				libNames = ["libv8", "libv8_libbase", "libv8_libplatform", "libchrome_zlib"]
				if PlatformType.Linux == platform:
					extensions = ['so']
				elif PlatformType.Android == platform:
					extensions = ['cr.so']
			return _generateLibPatterns(libNames, extensions)


		if os.path.isdir(outLibDir):
			shutil.rmtree(outLibDir)
		os.makedirs(outLibDir, exist_ok=True)

		if(not os.path.isdir(projectLibDir)):
			print(f"Error: Directory {projectLibDir} does not exist!")
		
		print(f'Packaging v8 in {outLibDir}')

		filePatterns = _getExpectedOutputFilePatterns(platform, buildConfig)

		if libraryType == V8.LibraryType.Static:
			# V8 emits the monolithic static library under obj/; package it with
			# the generic library name embedders consume.
			for root, dirs, files in os.walk(projectLibDir):
				for filename in files:
					libPath = os.path.join(root, filename)
					for pattern in filePatterns:
						if re.match(pattern, filename):
							outFilename = 'v8.lib' if platform == PlatformType.Windows else 'libv8.a'
							outPath = os.path.join(outLibDir, outFilename)
							print(f'\t{filename} -> {outFilename}')
							shutil.copy(libPath, outPath)
		else:
			for filename in os.listdir(projectLibDir):
				libPath = os.path.join(projectLibDir, filename)
				outPath = os.path.join(outLibDir, filename)
				if os.path.isfile(libPath):
					for pattern in filePatterns:
						if re.match(pattern, filename):
							print(f'\t{filename}')
							shutil.copy(libPath, outPath)

	def _setupWindowsEnv(self) -> EnvVars:
		env = os.environ.copy()
		self._ensureClangToolchain('clang-cl.exe', env)

		# Find available Visual Studio
		msvcPath = None
		vsVersion = "18"
		vsEditions = ['BuildTools', 'Professional', 'Community']
		programFilesDirs = [
			env.get('ProgramFiles', 'C:\\Program Files'),
			env.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'),
		]
		for programFilesDir in programFilesDirs:
			for edition in vsEditions:
				path = os.path.join(str(programFilesDir), 'Microsoft Visual Studio', vsVersion, edition, 'VC')
				if os.path.exists(path):
					msvcPath = path
					break
			if msvcPath is not None:
				break
		if msvcPath is None:
			raise RuntimeError("Error: Visual Studio install was not found in the possible paths!")
		# Setup environment for latest toolset
		vcVarsScript = os.path.join(msvcPath, "Auxiliary", "Build", "vcvarsall.bat")
		if not os.path.isfile(vcVarsScript):
			raise RuntimeError(f"Error: Visual Studio environment script was not found: {vcVarsScript}")
		vcVarsResult = subprocess.run(
			f'call "{vcVarsScript}" amd64 && set',
			shell=True,
			capture_output=True,
			text=True,
			env=env,
		)
		if vcVarsResult.returncode != 0:
			raise RuntimeError(
				f"Visual Studio environment setup failed:\n"
				f"{vcVarsResult.stdout}{vcVarsResult.stderr}"
			)
		vcArgs = vcVarsResult.stdout
		for line in vcArgs.splitlines():
			if '=' in line:
				key, value = line.split('=', 1)
				env[key] = value
		env[f'vs{vsVersion}_install'] = os.path.dirname(msvcPath)
		print(f'\t- Visual Studio {vsVersion} in {msvcPath}')
		toolset = env.get('VCToolsVersion')
		if toolset is None:
			raise RuntimeError("Error: MSVC toolset was not found!")
		print(f'\t- C++ Toolset {toolset}')

		env['DEPOT_TOOLS_WIN_TOOLCHAIN'] = '0'

		v8WinBuildTools = os.path.join(self._v8Dir, 'buildtools', 'win')
		if not os.path.exists(v8WinBuildTools):
			os.makedirs(v8WinBuildTools)
		shutil.copy(self._getBinExecutable('gn'), v8WinBuildTools)
		self._call([sys.executable, 'lastchange.py', '-o', 'LASTCHANGE'], 'build/util',env)
		return env

	def _setupLinuxEnv(self, arch: ArchType) -> EnvVars:
		env = os.environ.copy()
		self._ensureClangToolchain('clang', env)
		return env

	def _setupAndroidEnv(self) -> EnvVars:
		env = os.environ.copy()
		self._ensureClangToolchain('clang', env)
		self._call(
			[sys.executable, 'install-sysroot.py', '--arch=amd64'],
			'build/linux/sysroot_scripts',
			env,
		)
		return env

	def _ensureClangToolchain(self, compilerExecutable: str, env: EnvVars):
		clangDir = os.path.join(self._v8Dir, 'third_party', 'llvm-build', 'Release+Asserts')
		compiler = os.path.join(clangDir, 'bin', compilerExecutable)
		if not os.path.isfile(compiler):
			# Windows and WSL share this checkout but require different Clang
			# archives. Their revision stamps are identical, so remove the
			# incompatible archive before running the updater.
			if os.path.isdir(clangDir):
				shutil.rmtree(clangDir)
			print(f'\t- Installing Clang toolchain for {sysPlatform.system()}')
		self._call([sys.executable, 'update.py'], 'tools/clang/scripts', env)

	def _generateProject(self, projectPath: str, genArgs: dict, env: EnvVars):
		def _formatGnValue(value):
			if isinstance(value, bool):
				return str(value).lower()
			if isinstance(value, str):
				return f'"{value}"'
			if isinstance(value, list):
				return '[' + ', '.join(_formatGnValue(item) for item in value) + ']'
			return str(value)

		gnArgs = list()
		for k, v in genArgs.items():
			gnArgs.append(k + '=' + _formatGnValue(v))
		self._call([self._getBinExecutable('gn'), 'gen', projectPath, '--args=' + ' '.join(gnArgs)], '', env)
		if not os.path.isdir(projectPath):
			raise RuntimeError(f"\nExpected generated project directory to exist {projectPath}")

	def _compileProject(self, projectPath: str, target: str, env: EnvVars):
		args = [self._getBinExecutable('ninja'), '-C', projectPath]
		jobs = env.get('V8_PACKAGER_JOBS')
		if jobs:
			args.extend(['-j', jobs])
		args.append(target)
		self._call(args, '', env)

	def _getBinExecutable(self, name: str):
		file = os.path.join(self._binDir, f"{name}{'' if sysPlatform.system() == 'Linux' else '.exe'}")
		if not os.path.exists(file):
			raise RuntimeError(f"\nExpected to find V8 binary dependency '{name}'")
		return file

	def _call(self, args: List[str], dir: str, env: EnvVars):
		cwd = os.path.join(self._v8Dir, dir)
		result = subprocess.run(args, cwd=cwd, env=env)
		if result.returncode != 0:
			command = ' '.join(args)
			raise RuntimeError(f"Command failed with exit code {result.returncode}: {command}")
