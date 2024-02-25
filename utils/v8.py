
import io
import os
import re
import shutil
import subprocess
import sys
import zipfile
import requests
import platform as sysPlatform
from enum import Enum
from typing import List

import utils.git as git
from utils.types import ArchType, EnvVars, PlatformType, BuildConfig

class V8:
	class LibraryType(Enum):
		Shared = "Shared"
		Static = "Static"
		Monolithic = "Monolithic"

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
			self.libraryType: 'V8.LibraryType' = libraryType if libraryType is not None else V8.LibraryType.Shared
			self.defaultArgs = self._getDefaultArgs()
			pass

		def _getDefaultArgs(self):
			args = dict()
			# General
			args['use_custom_libcxx'] = False
			args['is_component_build'] = self.libraryType == V8.LibraryType.Shared 
			args['v8_static_library'] = self.libraryType == V8.LibraryType.Static or self.libraryType == V8.LibraryType.Monolithic
			args['v8_monolithic'] = self.libraryType == V8.LibraryType.Monolithic 

			# Validation/Debugging
			args['treat_warnings_as_errors'] = False
			args['fatal_linker_warnings'] = False
			args['v8_optimized_debug'] = True

			# Extensions
			args['v8_use_snapshot'] = False
			args['v8_use_external_startup_data'] = False
			args['v8_enable_verify_heap'] = False
			args['v8_enable_fast_mksnapshot'] = False
			args['v8_enable_fast_torque'] = False
			args['v8_enable_pointer_compression'] = True
			args['v8_enable_i18n_support'] = False

			return args

		def getBuildArgs(self, buildSettings: 'V8.BuildSettings'):
			args = self.defaultArgs.copy()

			# Platfrom
			args['is_clang'] = buildSettings.platform != PlatformType.Windows

			if PlatformType.Windows == buildSettings.platform:
				args['target_os'] = "win"
			elif PlatformType.Linux == buildSettings.platform:
				args['target_os'] = "linux"
			elif PlatformType.Android == buildSettings.platform:
				args['target_os'] = "android"
			else:
				raise  RuntimeError("Error: Unsupported Platform")

			if ArchType.x64 == buildSettings.arch:
				args['target_cpu'] = "x64"
			elif ArchType.Arm64 == buildSettings.arch:
				args['target_cpu'] = "arm64"
			else:
				raise  RuntimeError("Error: Unsupported CPU architecture")

			# Validation/Debugging
			args['is_debug'] = buildSettings.config == BuildConfig.Debug
			if buildSettings.config == BuildConfig.Release:
				args['symbol_level'] = 0

			return args
		
		def getCompileDefinitions(self) -> List[str]:
			defs = set()
			if self.defaultArgs.get('v8_enable_pointer_compression') == True:
				defs.add('V8_ENABLE_SANDBOX=1')
				defs.add('V8_COMPRESS_POINTERS=1')
				defs.add('V8_31BIT_SMIS_ON_64BIT_ARCH=1')

			if self.defaultArgs.get('v8_enable_31bit_smis_on_64bit_arch') == True:
				defs.add('V8_ENABLE_SANDBOX=1')
				defs.add('V8_31BIT_SMIS_ON_64BIT_ARCH=1')

			return list(defs)
		
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
	
	def fetchBinaryDependencies(self): 
		def _downloadBinaryFile(file, url, out):
			if os.path.exists(os.path.join(out, file)):
				return
			response = requests.get(url)
			if response.status_code == 200:
				zip_file = zipfile.ZipFile(io.BytesIO(response.content))
				os.makedirs(out, exist_ok=True)
				zip_file.extract(file, out)
				print(f"Downloaded '{file}'")
			else:
				print(f"Failed to download '{file}'")
		
		# We need prebuilt gn and ninja to compile the project
		ninjaUrl = "https://github.com/ninja-build/ninja/releases/download/v1.11.1/ninja-{}.zip"
		gnUrl = "https://chrome-infra-packages.appspot.com/dl/gn/gn/{}-amd64/+/latest"
		_downloadBinaryFile('ninja', ninjaUrl.format('linux'), self._binDir)
		_downloadBinaryFile('ninja.exe', ninjaUrl.format('win'), self._binDir)
		_downloadBinaryFile('gn', gnUrl.format('linux'), self._binDir)
		_downloadBinaryFile('gn.exe', gnUrl.format('windows'), self._binDir)

	def fetchProjectDependencies(self):
		requiredDeps = [
			'v8/build',
			'v8/base/trace_event/common',
			'v8/third_party/jinja2',
			'v8/third_party/markupsafe',
			'v8/third_party/googletest/src',
			'v8/third_party/zlib',
			'v8/tools/clang',

			# Android
			'v8/third_party/android_ndk',
			'v8/third_party/android_platform',
			'v8/third_party/catapult',
			'v8/third_party/colorama/src',
		]
		namespace = {}
		with open(os.path.join(self._v8Dir, 'DEPS')) as file:
			exec('Var = lambda name: vars[name]', namespace)
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

		gclientArgsFile = os.path.join(self._v8Dir, 'build/config/gclient_args.gni')
		if not os.path.isfile(gclientArgsFile) and os.path.exists(os.path.dirname(gclientArgsFile)):
			with open(gclientArgsFile, 'a') as f:
				f.write('declare_args() { checkout_google_benchmark = false }\n')

	def applyPatches(self):
		def _patchAndroid(v8Dir):
			# Find the correct prebuild clang libraries to update the patch
			prebuiltClangDir = os.path.join(v8Dir, 'third_party/android_ndk/toolchains/llvm/prebuilt/linux-x86_64/lib64/clang')
			for entry in os.scandir(prebuiltClangDir):
				if entry.is_dir():
					clangVersion = entry.name
					break
			if(not clangVersion):
				raise RuntimeError("Error: Expected Android prebuilt clang libraries")
			
			androidBuildFile = os.path.join(v8Dir, 'build/config/android/BUILD.gn')
			with open(androidBuildFile, 'r') as file:
				modifiedFile = re.sub(r'android_ndk_clang_version = ""', f'android_ndk_clang_version = "{clangVersion}"', file.read())
				with open(androidBuildFile, 'w') as file:
					file.write(modifiedFile)
		
		print('Configured Android prebuilt dependencies')

		# Apply available patches for the current version
		patchDirs = [
			os.path.join(self._patchDir, f'{self.version.major}'), 
	    	os.path.join(self._patchDir, f'{self.version.major}.{self.version.minor}')
		]
		for patchDir in patchDirs:
			for root, _, files in os.walk(patchDir):
				for file in files:
					if file.endswith('.patch'):
						file_path = os.path.join(root, file)
						git.applyPatch(os.path.abspath(file_path), 'v8')

		_patchAndroid(self._v8Dir)

	def build(self, outDir: str, projectSettings: ProjectSettings, buildSettingsList: List[BuildSettings]):
		outDir = os.path.abspath(outDir)
		buildSet = set()
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
				self.exportIncludes(os.path.join(buildOutDir, "include"))
				self.exportCompileDefinitions(buildOutDir, projectSettings)
				buildSet.add((buildSettings.platform, buildSettings.arch))

	def archive(self, archiveDir: str, buildDir: str):
		if os.path.isdir(archiveDir):
			shutil.rmtree(archiveDir)
		os.makedirs(archiveDir, exist_ok=True)
		print(f"Archiving libraries in '{archiveDir}'")
		for platformDir in os.listdir(buildDir):
			platformPath = os.path.join(buildDir, platformDir)
			if os.path.isdir(platformPath):
				for archDir in os.listdir(platformPath):
					archPath = os.path.join(platformPath, archDir)
					archiveFile = f"{platformDir}-{archDir}.zip"
					with zipfile.ZipFile(os.path.join(archiveDir, archiveFile), 'w') as archive:
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

	def exportCompileDefinitions(self, definitionsDir: str, projectSettings: ProjectSettings):
		os.makedirs(definitionsDir, exist_ok=True)
		defs = projectSettings.getCompileDefinitions()
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

		env = self._setupLinuxEnv(buildSettings.arch)
		self._compileAndExport(outLibDir, projectSettings, buildSettings, env)
		return True

	def _compileAndExport(self, outLibDir: str, projectSettings: ProjectSettings, buildSettings: BuildSettings, env):
		projectPath = os.path.join(self._v8Dir,'out.gn', buildSettings.platform.value.lower(), buildSettings.arch.value.lower(), buildSettings.config.value.lower())
		self._generateProject(projectPath, projectSettings.getBuildArgs(buildSettings), env)
		self._compileProject(projectPath, env)
		self._exportLibs(projectPath, outLibDir, buildSettings.platform, buildSettings.config)

	def _exportLibs(self, projectLibDir: str, outLibDir: str, platform: PlatformType, buildConfig: BuildConfig):
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

			libNames = []
			extensions = []
			if PlatformType.Windows == platform:
				libNames = ["v8", "v8_libbase", "v8_libplatform", "zlib"]
				extensions = ['dll', 'dll.lib']
				# if buildConfig == 'Debug':
				# 	extensions.append('dll.pdb')
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

		# Find available Visual Studio
		msvcPath = None
		vsVersion = "2022"
		vsEditions = ['Professional', 'Community']
		programFilesDir = env.get('ProgramFiles', 'C:\\Program Files')
		for edition in vsEditions:
			path = os.path.join(str(programFilesDir), 'Microsoft Visual Studio', vsVersion, edition, 'VC')
			if os.path.exists(path):
				msvcPath = path
				break
		if msvcPath == None:
			raise RuntimeError("Error: Visual Studio install was not found in the possible paths!")
		# Setup environment for latest toolset
		vcVarsScript = os.path.join(msvcPath, "Auxiliary", "Build", "vcvarsall.bat")
		vcArgs = subprocess.check_output(f'"{vcVarsScript}" amd64 && set', shell=True, universal_newlines=True, env=env)
		for line in vcArgs.splitlines():
			if '=' in line:
				key, value = line.split('=', 1)
				env[key] = value
		print(f'\t- Visual Studio {vsVersion} in {msvcPath}')
		toolset = env.get('VCToolsVersion')
		if toolset == None:
			raise RuntimeError("Error: MSVC toolset was not found!")
		print(f'\t- C++ Toolset {toolset}')

		env['DEPOT_TOOLS_WIN_TOOLCHAIN'] = '0'
		self._call([sys.executable, 'vs_toolchain.py', 'update'], 'build', env)

		v8WinBuildTools = os.path.join(self._v8Dir, 'buildtools', 'win')
		if not os.path.exists(v8WinBuildTools):
			os.makedirs(v8WinBuildTools)
		shutil.copy(self._getBinExecutable('gn'), v8WinBuildTools)
		self._call([sys.executable, 'lastchange.py', '-o', 'LASTCHANGE'], 'build/util',env)
		return env

	def _setupLinuxEnv(self, arch: ArchType) -> EnvVars:
		env = os.environ.copy()
		self._call([sys.executable, 'update.py'], 'tools/clang/scripts', env)
		if ArchType.x64 == arch:
			self._call([sys.executable, 'install-sysroot.py', '--arch=amd64'], 'build/linux/sysroot_scripts', env)
		elif ArchType.Arm64 == arch:
			self._call([sys.executable, 'install-sysroot.py', '--arch=arm64'], 'build/linux/sysroot_scripts', env)
		return env

	def _generateProject(self, projectPath: str, genArgs: dict, env: EnvVars):
		gnArgs = list()
		for k, v in genArgs.items():
			q = '"' if isinstance(v, str) else ''
			gnArgs.append(k + '=' + q + str(v) + q)
		self._call([self._getBinExecutable('gn'), 'gen', projectPath, '--args=' + ' '.join(gnArgs).lower()], '', env)
		if not os.path.isdir(projectPath):
			raise RuntimeError(f"\nExpected generated project directory to exist {projectPath}")

	def _compileProject(self, projectPath: str, env: EnvVars):
		self._call([self._getBinExecutable('ninja'), '-C', projectPath, 'v8'], '', env)

	def _getBinExecutable(self, name: str):
		file = os.path.join(self._binDir, f"{name}{'' if sysPlatform.system() == 'Linux' else '.exe'}")
		if not os.path.exists(file):
			raise RuntimeError(f"\nExpected to find V8 binary dependency '{name}'")
		return file

	def _call(self, args: List[str], dir: str, env: EnvVars):
		subprocess.check_call(args, cwd=os.path.join(self._v8Dir, dir), env=env)
