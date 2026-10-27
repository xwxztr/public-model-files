# Hi1711 openUBMC QEMU 离线源码包

本包来自 openUBMC/qemu，基于 QEMU 8.2.10，固定提交 755562f42e6dcd9b96563c312c054234eb73b957。
它提供 Hi1711 板型；不是官方 QEMU 11.1.2 的补丁包，也不会替换你已经安装的官方版本。

## 包含内容

- qemu/：该提交的完整受版本控制源码、许可证、已有固件二进制，以及递归展开的 ROM/测试 Git 子模块。
- 已展开的 Meson 子项目：dtc、libslirp、keycodemapdb、berkeley-softfloat-3、berkeley-testfloat-3、libblkio、libvfio-user。
- vendor/wheels/：Meson、tomli、pip、setuptools、wheel、Ninja 的固定版本离线包。
- reference/qemu_shells/：manifest 中的仿真启动脚本快照，仅供参考；不包含整套 openUBMC 固件应用仓，也不执行在线初始化。
- build-offline.sh：新增的离线构建入口，不运行原 build_qemu.sh，不拉 Git 子模块，不清理系统缓存。
- SOURCE_MANIFEST.json 与 INTERNAL_SHA256SUMS：上游来源、提交、依赖版本及包内文件校验。

仅使用公开源码和可公开分发工具。没有下载或包含厂商受限 SDK、账号、公司固件、L0/L1、内核、DTB 或根文件系统。

## 先校验，再解压

```bash
sha256sum -c SHA256SUMS
tar -xf openubmc-hi1711-offline-755562f42e6d.tar.xz
cd openubmc-hi1711-offline-755562f42e6d
sha256sum -c INTERNAL_SHA256SUMS
```

不要下载 Release 页面底部自动生成的 Source code.zip 来代替上面的附件。

## SUSE 15 SP7 环境要求

本包解决源码及 Python 构建工具的离线获取，不是可替代操作系统的完整 SDK。
使用你已经编译 QEMU 11.1.2 的容器即可继续检查：

- x86_64 Linux（附带的 Ninja wheel 面向 x86_64）。
- GCC >=7.4 或 Linux Clang >=10；建议沿用你已安装的 GCC 12/13。
- Python >=3.8，建议沿用 Python 3.11；需要 venv、ensurepip/pip、zlib。
- Make、Binutils、pkg-config、Perl、glibc 开发头文件。
- GLib/GModule >=2.56.0、zlib 开发包、pixman >=0.21.8。
- xattr 开发支持（系统 libc 足够时不另需库；否则 libattr-devel）。

常见 SUSE 包名（按实际仓库可见包安装，不进行全系统升级）：

```bash
zypper install make binutils pkg-config perl glibc-devel linux-glibc-devel \
  glib2-devel zlib-devel pixman-devel libattr-devel
```

GCC/Python 如已满足，不重复安装。若你用了 /opt 下的私有依赖，先加载先前的构建环境：

```bash
source /opt/qemu-build-11.1.2/env.sh
# 检查这些命令是否看到了你准备好的库：
pkg-config --modversion glib-2.0 gmodule-no-export-2.0 zlib pixman-1
```

本包从附带源码构建 libfdt；libslirp 缺少系统开发包时可使用附带子项目。
不需要 ARM 交叉编译器：你是在 x86_64 容器里构建运行于 x86_64 的 ARM 模拟器。

## 编译

```bash
# 路径按你实际安装的版本修改；普通系统 Python 3.11 可用 /usr/bin/python3.11。
QPYTHON=/usr/bin/python3.11 \
CC=/usr/bin/gcc-12 CXX=/usr/bin/g++-12 \
QJOBS=8 bash build-offline.sh
```

如果编译器默认版本已满足：

```bash
QPYTHON=python3.11 QJOBS=8 bash build-offline.sh
```

若私有 GLib 等通过 pkg-config 找到，但编译或链接仍缺头文件/库，给命令附加实际前缀，例如：

```bash
QPYTHON=python3.11 QJOBS=8 bash build-offline.sh \
  --extra-cflags='-I/opt/qemu-deps-11.1.2/include' \
  --extra-ldflags='-L/opt/qemu-deps-11.1.2/lib -Wl,-rpath,/opt/qemu-deps-11.1.2/lib'
```

默认仅构建 aarch64-softmmu，支持 TCG、slirp、9p 和工具。可用 QEMU_TARGETS 指定其他目标。
重新配置时给 QEMU_BUILD_DIR 指定新目录，避免旧缓存。本脚本不自动安装。

```bash
make -C build-hi1711 install
/opt/openubmc-qemu-hi1711/bin/qemu-system-aarch64 -machine help | grep hi1711
```

KVM 如有同架构 ARM 宿主且确有需要，可在构建命令末尾增加 --enable-kvm。
你当前 Xeon/x86_64 宿主模拟 ARM 使用 TCG。

## 测试与限制

```bash
export PATH="$PWD/.tools/bin:$PATH"
.tools/bin/meson test -C build-hi1711 --suite openubmc --print-errorlogs
```

私有 GLib 前缀还可能需要设置 LIBRARY_PATH（编译器链接路径）及 LD_LIBRARY_PATH（运行路径）。
受限沙箱中的 LeakSanitizer 可能因无法访问 /proc/<pid>/task 失败；应在正常 Linux 容器中复测，不能把这种失败当成已通过泄漏检查。

Release 附件中的 VALIDATION.txt 记录本次实际做过的检查及结果。
Ubuntu/Linux 上编译和测试通过，不等于已经在你的 SUSE 容器或真实固件上验证。
本包不承诺执行完整 L0/L1/U-Boot 启动链；官方示例主要从配套 Linux 内核、DTB、initrd 启动。
你公司的物理板 DTB/内核仍需逐项核对，不能直接认定与模型兼容。

## 为什么不直接运行原 build_qemu.sh

该上游脚本会重新初始化 ROM Git 子模块、处理 edk2、删除旧构建目录和部分临时文件。
本交付提供的 build-offline.sh 绕开这些在线/清理步骤；QEMU 核心 C 代码不作修改。
ROM 子模块完整展开，但重建各类 BIOS/UEFI 固件或启用 libblkio/libvfio-user 等其他功能，仍可能需要额外的交叉工具链、Rust crates 或系统开发包；本次离线构建脚本只选择上述 Hi1711 配置。
edk2 的原 subhook URL 已不可访问，本包从 TianoCore 官方镜像取得同一个提交，未使用占位文件；来源记录见 SOURCE_MANIFEST.json。

请保留 qemu/COPYING、COPYING.LIB、LICENSE 及各子项目许可证；再分发应按各自许可证处理。
