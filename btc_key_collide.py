import os
import sys
import time
import hashlib
from time import sleep

import ecdsa
import base58
import multiprocessing
import re
import signal
import threading
from multiprocessing import Process, Queue, Value, Event
from tqdm import tqdm

# ---------------------- 全局变量 ----------------------
stop_event = multiprocessing.Event()


# ---------------------- 信号处理 ----------------------
def signal_handler(sig, frame):
    print("\n接收到终止信号，正在清理进程...")
    stop_event.set()


# ---------------------- 核心地址生成函数 ----------------------
def generate_addresses(private_key=None):
    """生成压缩和非压缩地址"""
    if not private_key:
        private_key = os.urandom(32)

    sk = ecdsa.SigningKey.from_string(private_key, curve=ecdsa.SECP256k1)
    vk = sk.verifying_key
    x = vk.pubkey.point.x().to_bytes(32, 'big')
    y = vk.pubkey.point.y().to_bytes(32, 'big')

    # 生成压缩公钥
    compressed_prefix = b'\x02' if int.from_bytes(y, 'big') % 2 == 0 else b'\x03'
    compressed_pubkey = compressed_prefix + x

    # 生成非压缩公钥（04开头）
    uncompressed_pubkey = b'\x04' + x + y

    def make_address(pubkey):
        sha256 = hashlib.sha256(pubkey).digest()
        ripemd160 = hashlib.new('ripemd160', sha256).digest()
        version = b'\x00' + ripemd160
        checksum = hashlib.sha256(hashlib.sha256(version).digest()).digest()[:4]
        return base58.b58encode(version + checksum).decode('utf-8')

    return {
        'private_key': private_key.hex(),
        'compressed': make_address(compressed_pubkey),
        'uncompressed': make_address(uncompressed_pubkey)
    }


# ---------------------- 多进程工作器 ----------------------
def worker(target_addresses, total_iterations, result_queue, progress, stop_on_found):  # 修正参数数量
    """工作进程函数"""
    local_count = 0
    try:
        while not stop_event.is_set() and local_count < total_iterations // multiprocessing.cpu_count():
            # 生成密钥对
            data = generate_addresses()

            # 双地址校验
            match = False
            if data['compressed'] in target_addresses:
                result_queue.put(('compressed', data['compressed'], data['private_key']))
                match = True
            if data['uncompressed'] in target_addresses:
                result_queue.put(('uncompressed', data['uncompressed'], data['private_key']))
                match = True

            # 更新进度
            local_count += 1
            if local_count % 100 == 0:
                with progress.get_lock():
                    progress.value += 100

            # 发现匹配时立即暂停（可选）
            if match and stop_on_found.value:
                stop_event.set()

    except KeyboardInterrupt:
        pass


def load_addresses(filename):
    """地址加载函数"""
    btc_pattern = re.compile(r'^1[a-km-zA-HJ-NP-Z1-9]{25,34}$')
    try:
        with open(filename, 'r') as f:
            return set(line.strip() for line in f if btc_pattern.match(line.strip()))
    except FileNotFoundError:
        print(f"错误：文件 {filename} 未找到")
        sys.exit(1)


# ---------------------- 主程序 ----------------------
def main():
    # 初始化信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 加载地址库
    target_addresses = load_addresses('address_clean.txt')
    total_iterations = 10 ** 9
    num_cores = multiprocessing.cpu_count()

    # 共享变量
    progress = Value('i', 0)
    result_queue = Queue()
    stop_on_found = Value('b', True)  # 发现地址后是否停止

    # 结果处理线程（保持不变）
    def result_handler():
        while not stop_event.is_set():
            try:
                addr_type, address, privkey = result_queue.get(timeout=1)
                with open('foundkey.txt', 'a') as f:
                    f.write(f"[{addr_type.upper()}] {address}\nPrivate Key: {privkey}\n\n")
                print(f"\n发现匹配地址！类型：{addr_type}")
            except Exception:
                continue

    # 启动工作进程（参数数量修正）
    processes = []
    for _ in range(num_cores):
        p = Process(target=worker,
                    args=(target_addresses, total_iterations, result_queue, progress, stop_on_found))  # 5个参数
        p.start()
        processes.append(p)

    handler_thread = threading.Thread(target=result_handler)
    handler_thread.start()

    # 进度显示（保持不变）
    with tqdm(total=total_iterations, desc="碰撞进度", unit="次") as pbar:
        last_progress = 0
        while not stop_event.is_set():
            current = progress.value
            pbar.update(current - last_progress)
            last_progress = current
            if current >= total_iterations:
                stop_event.set()
            time.sleep(0.1)

    # 清理进程（保持不变）
    for p in processes:
        if p.is_alive():
            p.terminate()
        p.join()
    handler_thread.join()



if __name__ == '__main__':
    main()