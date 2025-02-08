import requests
import time

# 配置多个BTC余额查询API（按优先级排序）
API_CONFIGS = [
    {
        "name": "Blockchain.com",
        "url": "https://blockchain.info/balance?active={address}",
        "parser": lambda data, addr: data.get(addr, {}).get("final_balance", 0) / 1e8,
        "max_failures": 3,  # 最大允许失败次数
        "failures": 0,  # 当前失败计数
        "enabled": True  # 是否启用该API
    },
    {
        "name": "BlockCypher",
        "url": "https://api.blockcypher.com/v1/btc/main/addrs/{address}/balance",
        "parser": lambda data, _: data.get("final_balance", 0) / 1e8,
        "max_failures": 3,
        "failures": 0,
        "enabled": True
    },
    {
        "name": "Blockchair",
        "url": "https://api.blockchair.com/bitcoin/dashboards/address/{address}",
        "parser": lambda data, _: data.get("data", {}).get(addr, {}).get("address", {}).get("balance", 0) / 1e8,
        "max_failures": 3,
        "failures": 0,
        "enabled": True
    }
]

# 全局配置
MIN_BTC = 0.5  # 最小保留余额
REQUEST_TIMEOUT = 10  # 请求超时时间（秒）
SLEEP_BETWEEN_REQUESTS = 1  # 请求间隔（秒）


def get_btc_balance(address):
    """通过多个API获取BTC余额，自动切换稳定接口"""
    for api in API_CONFIGS:
        if not api["enabled"]:
            continue

        try:
            # 发送请求
            url = api["url"].format(address=address)
            response = requests.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()

            # 解析数据
            data = response.json()
            balance = api["parser"](data, address)

            # 重置失败计数
            api["failures"] = 0
            return balance

        except Exception as e:
            # 记录失败并检查是否禁用API
            api["failures"] += 1
            print(f"[{api['name']}] 请求失败: {str(e)}")

            if api["failures"] >= api["max_failures"]:
                api["enabled"] = False
                print(f"[警告] 已禁用 {api['name']}，因连续失败超过阈值")

            time.sleep(SLEEP_BETWEEN_REQUESTS)  # 失败后稍作等待

    # 所有API均失败
    print("所有API均不可用，无法获取余额")
    return None


def filter_addresses():
    buffer = []

    try:
        # 初始化输出文件
        with open("address_clear_1.txt", "w") as f:
            pass

        # 读取地址
        with open("address_clean.txt", "r") as f:
            addresses = [line.strip() for line in f if line.strip()]

        total = len(addresses)
        for idx, address in enumerate(addresses, 1):
            print(f"\n▶ 处理进度: {idx}/{total} | 当前地址: {address}")

            balance = get_btc_balance(address)
            if balance is None:
                print("→ 跳过（余额查询失败）")
                continue

            if balance >= MIN_BTC:
                buffer.append(address)
                print(f"→ 保留（余额: {balance:.8f} BTC）")

                # 每满10个立即写入
                if len(buffer) >= 10:
                    with open("address_clear_1.txt", "a") as f:
                        f.write("\n".join(buffer) + "\n")
                    buffer = []
                    print("✓ 已写入10个地址到文件")
            else:
                print(f"→ 移除（余额不足: {balance:.8f} BTC）")

            time.sleep(SLEEP_BETWEEN_REQUESTS)

        # 写入剩余地址
        if buffer:
            with open("address_clear_1.txt", "a") as f:
                f.write("\n".join(buffer))
            print(f"✓ 最后写入 {len(buffer)} 个地址")

        print("\n筛选完成！结果文件: address_clear_1.txt")

    except FileNotFoundError:
        print("错误: 输入文件 address_clean.txt 不存在")
    except Exception as e:
        print(f"程序异常: {str(e)}")


if __name__ == "__main__":
    filter_addresses()