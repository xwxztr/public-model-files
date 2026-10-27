#!/usr/bin/env python3
"""Recreate the reviewed Hi1711 source bundle on a disposable GitHub runner."""
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

PIN = '755562f42e6dcd9b96563c312c054234eb73b957'
MANIFEST_PIN = '523184ae195b255eeadb0aeefe627f3ab01687a9'
NAME = 'openubmc-hi1711-offline-755562f42e6d'
HERE = Path(__file__).resolve().parent
WORK = Path(os.environ.get('HI1711_WORK', 'hi1711-work')).resolve()
SRC = WORK / 'source/qemu'
REF = WORK / 'source/manifest'
DIST = WORK / 'dist'
STAGE = WORK / 'stage' / NAME

HASHES = {
 'meson-1.2.3-py3-none-any.whl':'17d9124ffad38f5bbb6b198a8de5ecc55ebcd164d35a1d9dae06b8de0605a252',
 'ninja-1.11.1.3-py3-none-manylinux_2_12_x86_64.manylinux2010_x86_64.whl':'a27e78ca71316c8654965ee94b286a98c83877bfebe2607db96897bbfe458af0',
 'pip-24.0-py3-none-any.whl':'ba0d021a166865d2265246961bec0152ff124de910c5cc39f1156ce3fa7c69dc',
 'setuptools-69.5.1-py3-none-any.whl':'c636ac361bc47580504644275c9ad802c50415c7522212252c033bd15f301f32',
 'tomli-2.0.1-py3-none-any.whl':'939de3e7a6161af0c887ef91b7d41a53e7c5a1ca976325f429cb46ea9bc30ecc',
 'wheel-0.43.0-py3-none-any.whl':'55c570405f142630c6b9f72fe09d9b67cf1477fcf543ae5b8dcb1f5b7377da81',
 'glib-2.78.6.tar.xz':'244854654dd82c7ebcb2f8e246156d2a05eb9cd1ad07ed7a779659b4602c9fae',
 'libffi-3.4.6.tar.gz':'b0dea9df23c863a7a50e825440f3ebffabd65df1497108e5d437747843895a4e',
 'pixman-0.44.2.tar.gz':'6349061ce1a338ab6952b92194d1b0377472244208d47ff25bef86fc71973466',
 'pkgconf-2.2.0.tar.xz':'b06ff63a83536aa8c2f6422fa80ad45e4833f590266feb14eaddfe1d4c853c69',
}
URLS = {
 'glib-2.78.6.tar.xz':'https://download.gnome.org/sources/glib/2.78/glib-2.78.6.tar.xz',
 'libffi-3.4.6.tar.gz':'https://github.com/libffi/libffi/releases/download/v3.4.6/libffi-3.4.6.tar.gz',
 'pixman-0.44.2.tar.gz':'https://www.cairographics.org/releases/pixman-0.44.2.tar.gz',
 'pkgconf-2.2.0.tar.xz':'https://distfiles.ariadne.space/pkgconf/pkgconf-2.2.0.tar.xz',
}

def run(*args, cwd=None, env=None):
    print('+', ' '.join(map(str,args)),flush=True)
    subprocess.run(list(map(str,args)), cwd=cwd, env=env, check=True)

def git(repo,*args):
    return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):h.update(block)
    return h.hexdigest()

def clone(url,pin,dest):
    dest.mkdir(parents=True)
    run('git','init',dest)
    run('git','-C',dest,'remote','add','origin',url)
    run('git','-C',dest,'fetch','--depth','1','origin',pin)
    run('git','-C',dest,'checkout','--detach','FETCH_HEAD')
    assert git(dest,'rev-parse','HEAD')==pin

def export(repo,dest):
    dest.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=WORK) as td:
        p=Path(td)/'source.tar'
        run('git','-C',repo,'archive','--format=tar','--output',p,'HEAD')
        run('tar','-xf',p,'-C',dest)

def status(repo):
    text=subprocess.check_output(['git','-C',str(repo),'submodule','status','--recursive'],text=True)
    assert all(line.startswith(' ') for line in text.splitlines()),text
    return [(line.strip().split()[0],line.strip().split()[1]) for line in text.splitlines()]

def prepare():
    WORK.mkdir(parents=True,exist_ok=True)
    DIST.mkdir(parents=True,exist_ok=True)
    clone('https://gitcode.com/openUBMC/qemu.git',PIN,SRC)
    run('git','submodule','update','--init','--jobs','6','--depth','1',cwd=SRC)
    edk=SRC/'roms/edk2'
    run('git','config','submodule.UnitTestFrameworkPkg/Library/SubhookLib/subhook.url',
        'https://github.com/tianocore/edk2-subhook.git',cwd=edk)
    run('git','submodule','update','--init','--recursive','--jobs','6','--depth','1',cwd=SRC)
    subs=status(SRC)
    assert len(subs)==34,subs
    clone('https://gitcode.com/openUBMC/manifest.git',MANIFEST_PIN,REF)
    prep=WORK/'prep-meson'
    run(sys.executable,'-m','pip','install','--no-index','--target',prep,
        SRC/'python/wheels/meson-1.2.3-py3-none-any.whl')
    env=dict(os.environ,PYTHONPATH=str(prep))
    projects=sorted(p.stem for p in (SRC/'subprojects').glob('*.wrap'))
    assert len(projects)==7,projects
    run(sys.executable,'-m','mesonbuild.mesonmain','subprojects','download',*projects,cwd=SRC,env=env)
    export(SRC,STAGE/'qemu')
    subrecords=[]
    for commit,path in subs:
        repo=SRC/path
        assert git(repo,'rev-parse','HEAD')==commit
        export(repo,STAGE/'qemu'/path)
        subrecords.append({'path':path,'commit':commit,'origin':git(repo,'remote','get-url','origin')})
    wraps=[]
    for wrap in sorted((SRC/'subprojects').glob('*.wrap')):
        cfg=configparser.ConfigParser(interpolation=None)
        cfg.read(wrap)
        repo=SRC/'subprojects'/wrap.stem
        commit=git(repo,'rev-parse','HEAD')
        assert commit==cfg['wrap-git']['revision']
        status(repo)
        shutil.copytree(repo,STAGE/'qemu/subprojects'/wrap.stem,symlinks=True,
                        ignore=shutil.ignore_patterns('.git'),dirs_exist_ok=True)
        wraps.append({'name':wrap.stem,'commit':commit,'url':cfg['wrap-git']['url'],
                      'meson_patch_directory':cfg['wrap-git'].get('patch_directory')})
    wheels=STAGE/'vendor/wheels'
    wheels.mkdir(parents=True)
    for wheel in (SRC/'python/wheels').glob('*.whl'):shutil.copy2(wheel,wheels/wheel.name)
    run(sys.executable,'-m','pip','download','--only-binary=:all:','--dest',wheels,
        'pip==24.0','setuptools==69.5.1','wheel==0.43.0','ninja==1.11.1.3')
    deps=STAGE/'vendor/dependency-sources'
    deps.mkdir(parents=True)
    for name,url in URLS.items():
        urllib.request.urlretrieve(url,deps/name)
    records=[]
    for root in (wheels,deps):
        for p in sorted(root.iterdir()):
            assert sha(p)==HASHES[p.name],p
            records.append({'file':p.name,'sha256':HASHES[p.name]})
    for name in ('README_zh.md','build-offline.sh'):shutil.copy2(HERE/name,STAGE/name)
    os.chmod(STAGE/'build-offline.sh',0o755)
    shutil.copytree(REF/'build/works/packet/qemu_shells',STAGE/'reference/qemu_shells')
    manifest={'project':'openUBMC/qemu','url':'https://gitcode.com/openUBMC/qemu.git',
              'commit':PIN,'upstream_version':(SRC/'VERSION').read_text().strip(),
              'git_submodules':subrecords,'meson_subprojects':wraps,
              'manifest_reference_commit':MANIFEST_PIN,
              'subhook_note':'Original Zeex URL unavailable; official TianoCore mirror provides identical commit 83d4e1ebef3588fae48b69a7352cc21801cb70bc.',
              'code_modifications':'No QEMU C source changes. Meson wrap overlays applied. Added offline build wrapper and documentation. Git history omitted.',
              'wheels':[r for r in records if r['file'].endswith('.whl')],
              'dependency_sources':[r for r in records if not r['file'].endswith('.whl')]}
    (STAGE/'SOURCE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print('All 34 recursive Git submodules and 7 Meson projects exported.',flush=True)

def finalize():
    assert STAGE.is_dir()
    for p in list((STAGE/'qemu').rglob('__pycache__')):
        if p.is_dir() and not p.is_symlink():shutil.rmtree(p)
    files=[];links=[]
    for p in sorted(STAGE.rglob('*')):
        rel=p.relative_to(STAGE)
        if rel.parts[0]=='.tools':continue
        if p.is_symlink():links.append({'path':str(rel),'target':os.readlink(p)})
        elif p.is_file() and p.name!='INTERNAL_SHA256SUMS':files.append(p)
    (STAGE/'SYMLINKS.json').write_text(json.dumps(links,indent=2)+'\n')
    files=sorted(set(files+[STAGE/'SYMLINKS.json']))
    with (STAGE/'INTERNAL_SHA256SUMS').open('w') as out:
        for p in files:
            if p.stat().st_size < 2048:
                assert not p.read_bytes().startswith(b'version https://git-lfs.github.com/spec/v1'),p
            out.write(sha(p)+'  '+str(p.relative_to(STAGE))+'\n')
    archive=DIST/(NAME+'.tar.xz')
    env=dict(os.environ,XZ_OPT='-T2 -3')
    run('tar','--sort=name','--mtime=2026-10-24 12:08:29Z','--owner=0','--group=0','--numeric-owner',
        '--exclude='+NAME+'/.tools','--exclude=*/__pycache__','-cJf',archive,'-C',STAGE.parent,NAME,env=env)
    expected=None;seen=set();actual_links={};linkmap={}
    with tarfile.open(archive,'r|xz') as tar:
        for m in tar:
            parts=Path(m.name).parts
            assert parts[0]==NAME and '.git' not in parts and '.tools' not in parts,m.name
            rel='/'.join(parts[1:])
            if m.issym():actual_links[rel]=m.linkname;continue
            if not m.isfile():continue
            src=tar.extractfile(m)
            if rel=='INTERNAL_SHA256SUMS':
                expected={line[66:]:line[:64] for line in src.read().decode().splitlines()}
                continue
            assert expected is not None
            h=hashlib.sha256();data=[] if rel=='SYMLINKS.json' else None
            for block in iter(lambda:src.read(1048576),b''):
                h.update(block)
                if data is not None:data.append(block)
            assert expected.get(rel)==h.hexdigest(),rel
            seen.add(rel)
            if data is not None:linkmap={r['path']:r['target'] for r in json.loads(b''.join(data))}
    assert seen==set(expected)
    assert linkmap==actual_links
    shutil.copy2(STAGE/'README_zh.md',DIST/'README_zh.md')
    report={'archive':archive.name,'size_bytes':archive.stat().st_size,
            'verified_regular_files':len(seen),'verified_symlinks':len(actual_links),
            'git_submodules':34,'meson_subprojects':7,'archive_integrity':'PASS'}
    (DIST/'ARCHIVE_VERIFICATION.json').write_text(json.dumps(report,indent=2)+'\n')
    with (DIST/'SHA256SUMS').open('w') as out:
        for p in (archive,DIST/'README_zh.md',DIST/'VALIDATION.txt',DIST/'ARCHIVE_VERIFICATION.json'):
            out.write(sha(p)+'  '+p.name+'\n')
    notes='''Hi1711 openUBMC QEMU 完整离线源码包

基于 QEMU 8.2.10，openUBMC 提交 `755562f42e6dcd9b96563c312c054234eb73b957`。
包含全部 34 个递归 Git 子模块、7 个 Meson 子项目和固定版本离线 Python 构建工具。
GitHub Actions 对导出源码进行了编译、Hi1711 板型检查、openubmc 回归测试和归档逐文件校验。
SUSE 系统仍需已有 GCC/Python、GLib/zlib/pixman 等开发环境；入口为 `build-offline.sh`。
没有包含公司固件或受限厂商 SDK；未验证用户自己的 L0/L1/U-Boot/内核启动。

请下载 Assets 中的 `openubmc-hi1711-offline-755562f42e6d.tar.xz`，以及说明、校验和验证报告。
不要以底部自动生成的 Source code ZIP 代替完整附件。

Archive SHA256: `'''+sha(archive)+'`\n'
    (WORK/'release-notes.md').write_text(notes)
    print(json.dumps(report),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('phase',choices=['prepare','finalize'])
    args=parser.parse_args()
    {'prepare':prepare,'finalize':finalize}[args.phase]()
