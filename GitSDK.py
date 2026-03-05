"""
Git 自动更新模块
整合了 Git 仓库管理和 mirror 加速更新功能
支持完全配置化，可迁移到任意项目使用
"""

import configparser
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional, Callable
from logger import SimpleLogger

@dataclass
class GitConfig:
    """Git 更新配置"""
    repository: str = "https://github.com/name/test.git"
    branch: str = "master"
    git_path: str = "git"
    proxy: Optional[str] = None
    ssl: bool = True
    update: bool = True
    keep_changes: bool = False
    mirror: bool = False
    mirror_url: str = ""
    depth: Optional[int] = None  # 浅克隆深度，None 表示完整克隆
    
    # 日志回调 (可选）（其它自行实现日志系统调用方法）
    log_callback: Optional[Callable[[str], None]] = None
    
    def __post_init__(self):
        if self.git_path:
            self.git_path = self.git_path.replace('\\', '/')
        if self.mirror_url:
            self.mirror_url = self.mirror_url.strip('/')


class GitSDK:
    """Git 仓库py接口"""
    
    def __init__(self, config: GitConfig, folder: Optional[str] = None):
        """
        Args:
            config: Git 配置对象
            folder: 项目根目录，默认为当前目录
        """
        self.config = config
        self.folder = folder or os.getcwd()
        self.logger = SimpleLogger(config.log_callback)
        # 切换到项目目录以便执行git命令
        os.chdir(self.folder)
        self.git_config = configparser.ConfigParser()
        self.git_config.read('./.git/config')
    @property
    def git(self) -> str:
        """获取 git 可执行文件路径"""
        exe = self.config.git_path
        if exe and os.path.exists(exe):
            return exe
        return 'git'
    @staticmethod
    def delete(file: str):
        """删除文件"""
        try:
            os.remove(file)
            print(f'Remove {file}')
        except FileNotFoundError:
            print(f'File not found: {file}')
    
    def config_eq(self, section: str, option: str, value: Optional[str]) -> bool:
        """
        检查本地 git 配置项是否匹配
        
        Args:
            section: 配置节
            option: 配置项
            value: 期望值
            
        Returns:
            bool: 是否匹配
        """
        result = self.git_config.get(section, option, fallback=None)
        if result == value:
            self.logger.info(f'Git config {section}.{option} = {value}')
            return True
        else:
            self.logger.warning(f'Git config {section}.{option} != {value}')
            return False
    
    def run_cmd(self, command: str, allow_failure: bool = False, output: bool = True, return_output: bool = False) -> bool | str:
        """
        执行命令
        
        Args:
            command: 命令字符串
            allow_failure: 是否允许失败
            output: 是否输出日志（仅在 return_output=False 时生效）
            return_output: 是否返回命令输出（True 时返回 stdout）
            
        Returns:
            bool | str: 返回布尔值表示成功与否，或当 return_output=True 时返回命令输出
        """
        command = command.replace(r"\\", "/").replace("\\", "/")
        self.logger.info(f'Run command: {command}')
        if return_output:
            result = subprocess.run(
                command, capture_output=True, text=True, encoding="utf8", shell=True
            )
            if output:
                if result.stdout:
                    self.logger.info(result.stdout)
                if result.stderr:
                    self.logger.info(result.stderr)
            
            if result.returncode and not allow_failure:
                self.logger.info(f'[ Command Error ], error_code: {result.returncode}')
                raise Exception(f"Command failed: {command}")
            return result.stdout
        else:
            error_code = os.system(command)
            if error_code:
                if allow_failure:
                    self.logger.warning(f'[ Command Error ], error_code: {error_code}')
                    return False
                else:
                    self.logger.info(f'[ Command Error ], error_code: {error_code}')
                    raise Exception(f"Command failed: {command}")
            else:
                self.logger.info(f'[ Command Success ]{command}')
                return True
    
    def mirror_repo(self, repo_url: str) -> str:
        """
        将仓库 URL 转换为 mirror 加速 URL
        
        Args:
            repo_url: 原始仓库 URL
            
        Returns:
            str: mirror 加速后的 URL
        """
        if not self.config.mirror or not self.config.mirror_url:
            return repo_url
        
        mirror_base = self.config.mirror_url.rstrip('/')
        # 处理 github.com 的 URL
        if 'github.com' in repo_url:
            # https://github.com/user/repo.git -> https://mirror.com/github.com/user/repo.git
            repo_path = repo_url.replace('https://', '').replace('http://', '')
            return f'{mirror_base}/{repo_path}'
        
        return repo_url
    
    def git_repo_init(self, repo: str, source: str = 'origin',
                      branch: str = 'master', proxy: Optional[str] = '',
                      ssl: bool = True, keep_changes: bool = False,
                      depth: Optional[int] = None):
        """
        初始化 git 仓库并拉取代码
        
        Args:
            repo: 仓库地址
            source: remote 名称
            branch: 分支名称
            proxy: 代理地址
            ssl: 是否验证 SSL
            keep_changes: 是否保留本地修改
            depth: 浅克隆深度，None 表示完整克隆
        """
        # 应用 mirror 加速
        repo = self.mirror_repo(repo)
        
        # 修复仓库
        if not self.run_cmd(f'"{self.git}" init', allow_failure=True):
            for file in ['./.git/HEAD','./.git/ORIG_HEAD','./.git/config','./.git/index', ]:
                self.delete(file)
            self.run_cmd(f'"{self.git}" init')
        
        # 设置代理
        if proxy:
            self.logger.info('Set Git Proxy')
            if not self.config_eq('http', 'proxy', value=proxy):
                self.run_cmd(f'"{self.git}" config --local http.proxy {proxy}')
            if not self.config_eq('https', 'proxy', value=proxy):
                self.run_cmd(f'"{self.git}" config --local https.proxy {proxy}')
        else:
            self.logger.info('No Proxy')
            if not self.config_eq('http', 'proxy', value=None):
                self.run_cmd(f'"{self.git}" config --local --unset http.proxy', allow_failure=True)
            if not self.config_eq('https', 'proxy', value=None):
                self.run_cmd(f'"{self.git}" config --local --unset https.proxy', allow_failure=True)
        
        # 设置 SSL 验证
        if ssl:
            if not self.config_eq('http', 'sslVerify', value='true'):
                self.run_cmd(f'"{self.git}" config --local http.sslVerify true', allow_failure=True)
        else:
            self.logger.warning('SSL verify is closed')
            if not self.config_eq('http', 'sslVerify', value='false'):
                self.run_cmd(f'"{self.git}" config --local http.sslVerify false', allow_failure=True)
        
        # 设置远程仓库
        if not self.config_eq(f'remote "{source}"', 'url', value=repo):
            if not self.run_cmd(f'"{self.git}" remote set-url {source} {repo}', allow_failure=True):
                self.run_cmd(f'"{self.git}" remote add {source} {repo}')
        
        # Fetch 分支，可能因网络原因失败
        fetch_cmd = f'"{self.git}" fetch {source} {branch}'
        if depth is not None:
            fetch_cmd += f' --depth={depth}'
        if not self.run_cmd(fetch_cmd, allow_failure= True):
            self.logger.info('Fetch failed, retry')
            self.run_cmd(fetch_cmd)
        
        # Pull 分支
        # 移除 git lock 文件
        for file in ['./.git/HEAD.lock','./.git/index.lock','./.git/refs/heads/master.lock',]:
            if os.path.exists(file):
                self.logger.info(f'Remove Lock file {file}')
                self.delete(file)
        
        # 构建 pull 命令，支持 depth 参数
        pull_cmd = f'"{self.git}" pull --ff-only {source} {branch}'
        if depth is not None:
            pull_cmd += f' --depth={depth}'
        
        if keep_changes:
            if self.run_cmd(f'"{self.git}" stash', allow_failure=True):
                self.run_cmd(pull_cmd)
                if self.run_cmd(f'"{self.git}" stash pop', allow_failure=True):
                    pass
                else:
                    self.logger.info('Stash pop failed, no local modifications')
            else:
                self.logger.info('Stash failed, discarding modifications')
                self.run_cmd(f'"{self.git}" reset --hard {source}/{branch}')
                self.run_cmd(pull_cmd)
        else:
            self.run_cmd(f'"{self.git}" reset --hard {source}/{branch}')
            # Since `git fetch` is already called, checkout is faster
            if not self.run_cmd(f'"{self.git}" checkout {branch}', allow_failure=True):
                self.run_cmd(pull_cmd)
        
        # 显示当前分支版本
        self.run_cmd(f'"{self.git}" --no-pager log --no-merges -1')
    
    def update(self):
        """
        执行更新
        
        Returns:
            bool: 是否更新成功
        """
        self.logger.info('Start Git')
        
        if not self.config.update:
            self.logger.info('Disable update, skip')
            return True
        try:
            self.git_repo_init(
                repo=self.config.repository,
                source='origin',
                branch=self.config.branch,
                proxy=self.config.proxy,
                ssl=self.config.ssl,
                keep_changes=self.config.keep_changes,
                depth=self.config.depth,
            )
        except Exception as e:
            self.logger.error(f'Git update failed{e}')
            return False
        return True
    
    def check_update(self) -> bool:
        """
        检查是否有更新
        
        Returns:
            bool: 是否有可用更新
        """
        # 使用 git fetch 检查
        source = "origin"
        branch = self.config.branch
        git = self.git

        if not self.run_cmd(f'"{git}" fetch {source} {branch}', allow_failure=True):
            self.logger.warning("Failed git fetch")
            return False
        
        # 检查是否有新提交
        log = self.run_cmd(
            f'"{git}" log --not --remotes={source}/* -1 --oneline'
        ,return_output= True)
        if log:
            self.logger.info(
                f"You can't update because Local commit {log.split()[0]} is not update to upstream repository"
            )
            return False
        
        # 获取当前分支落后于远程分支的那些提交
        output = self.run_cmd(
            f'"{git}" log ..{source}/{branch} --pretty=format:"%an|||%ad|||%s|||%H" --date=iso -1'
        ,return_output= True)
        if output:
            output = output.split("|||")
            if len(output) >= 4:
                author, date, message, hash1 = output[0], output[1], output[2], output[3]
                self.logger.info(f"Updates detected")
                self.logger.info(f"{hash1[:8]} - {message}")
                return True
        
        self.logger.info("Repo is current commit")
        return False
    
    def deepen(self, depth: int = 1, unshallow: bool = False):
        """
        深化浅克隆深度或转换为完整仓库,本地日志缺失可以调用本函数还原
        """
        source = "origin"
        branch = self.config.branch
        git = self.git
        
        if unshallow:
            # 转换为完整仓库
            self.logger.info("Converting to full repository")
            cmd = f'"{git}" fetch --unshallow'
            if not self.run_cmd(cmd, allow_failure=True):
                self.logger.warning("Failed to unshallow, because it is a complete repository now")
                return False
        elif depth is not None:
            # 在现有基础上增加深度
            if depth > 0:
                self.logger.info(f"Deepening by {depth} layers from current shallow boundary")
                cmd = f'"{git}" fetch --deepen={depth}'
            else:
                self.logger.info("No depth change needed")
                return False
            self.run_cmd(cmd)
        
        # 重置到最新提交
        self.run_cmd(f'"{git}" reset --hard {source}/{branch}')
        
        # 显示当前版本
        self.run_cmd(f'"{git}" --no-pager log --no-merges -1')
        return True


def git_by_ini(use_dev = False):
    # 读取 INI 配置文件，优先读取 dev_config.ini
    config_file = os.path.join(os.path.dirname(__file__), 'dev_config.ini')
    if (not os.path.exists(config_file)) or (not use_dev):
        config_file = os.path.join(os.path.dirname(__file__), 'config.ini')
    
    if not os.path.exists(config_file):
        print(f"错误：配置文件不存在 - {config_file}")
        return False

    parser = configparser.ConfigParser()
    parser.read(config_file, encoding='utf-8')

    # 从 INI 文件读取参数
    repo = parser.get('git', 'repository')
    branch = parser.get('git', 'branch')
    git_path = parser.get('git', 'git_path')

    # 如果 git_path 是相对路径，转换为绝对路径
    if not os.path.isabs(git_path):
        git_path = os.path.join(os.path.dirname(__file__), git_path).replace('\\', '/')

    update = parser.getboolean('update', 'update')
    keep_changes = parser.getboolean('update', 'keep_changes')
    use_mirror = parser.getboolean('update', 'mirror')
    mirror_url = parser.get('update', 'mirror_url', fallback='')
    depth_str = parser.get('update', 'depth', fallback='')
    depth = int(depth_str) if depth_str.strip() else None

    proxy = parser.get('network', 'proxy', fallback=None)
    ssl = parser.getboolean('network', 'ssl')

    project_folder = parser.get('paths', 'project_folder', fallback=None)
    if project_folder and not os.path.isabs(project_folder):
        # 如果是相对路径，相对于 GitSDK.py 所在目录转换
        project_folder = os.path.join(os.path.dirname(__file__), project_folder)
    elif not project_folder or project_folder.strip() == '':
        project_folder = os.getcwd()

    # 创建配置并执行更新
    updater = create(
        repo,
        branch,
        git_path,
        proxy,
        ssl,
        update,
        keep_changes,
        use_mirror,
        mirror_url,
        depth,
        project_folder,
    )

    success = updater.update()
    print(f"更新结果：{'成功' if success else '失败'}\n")
    return success
def create(
    repository: str,
    branch: str = 'master',
    git_path: str = 'git',
    proxy_port: Optional[str] = None,
    ssl_verify: bool = True,
    need_update: bool = True,
    keep_changes: bool = False,
    use_mirror: bool = False,
    mirror_url: str = '',
    depth: Optional[int] = None,
    folder: Optional[str] = None,
    log_callback: Optional[Callable[[str], None]] = None,
) -> GitSDK:
    """
    创建 Git 更新器的便捷函数
    
    Args:
        repository: Git 仓库地址
        branch: 分支名称
        git_path: git 可执行文件路径
        proxy_port: 代理地址
        ssl_verify: 是否验证 SSL
        need_update: 是否自动更新
        keep_changes: 是否保留本地修改
        use_mirror: 是否使用 mirror
        mirror_url: mirror 地址
        folder: 项目根目录
        log_callback: 日志回调函数
        depth: 浅克隆深度，None 表示完整克隆
        
    Returns:
        GitSDK 实例
    """
    config = GitConfig(
        repository=repository,
        branch=branch,
        git_path=git_path,
        proxy=proxy_port,
        ssl=ssl_verify,
        update=need_update,
        keep_changes=keep_changes,
        mirror=use_mirror,
        mirror_url=mirror_url,
        depth=depth,
        log_callback=log_callback,
    )
    return GitSDK(config, folder)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Git 自动更新工具')
    parser.add_argument('--repo', type=str, required=True, help='Git 仓库地址')
    parser.add_argument('--branch', type=str, default='master', help='分支名称')
    parser.add_argument('--git', type=str, default='git', help='git 可执行文件路径')
    parser.add_argument('--proxy', type=str, default=None, help='HTTP 代理')
    parser.add_argument('--no-ssl-verify', action='store_true', help='不验证 SSL')
    parser.add_argument('--no-auto-update', action='store_true', help='禁用自动更新')
    parser.add_argument('--keep-changes', action='store_true', help='保留本地修改')
    parser.add_argument('--use-mirror', action='store_true', help='使用 mirror 加速')
    parser.add_argument('--mirror-url', type=str, default='', help='mirror 地址')
    parser.add_argument('--folder', type=str, default=None, help='项目根目录')
    parser.add_argument('--check-only', action='store_true', help='仅检查更新，不执行更新')
    parser.add_argument('--depth', type=int, default=None, help='浅克隆深度')
    parser.add_argument('--unshallow', action='store_true', help='转换为完整仓库（获取所有历史）')
    
    args = parser.parse_args()
    config = GitConfig(
        repository=args.repo,
        branch=args.branch,
        git_path=args.git,
        proxy=args.proxy,
        ssl=not args.no_ssl_verify,
        update=not args.no_auto_update,
        keep_changes=args.keep_changes,
        mirror=args.use_mirror,
        mirror_url=args.mirror_url,
        depth=args.depth,
    )
    SDK = GitSDK(config, folder=args.folder)
    if args.check_only:
        state = SDK.check_update()
    elif args.unshallow:
        state=SDK.deepen(unshallow=True)
    else:
        state = SDK.update()
    sys.exit(0 if state else 1)
