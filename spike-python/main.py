"""CLIConductor Spike — Python + FastAPI

Milestone 1: 单 Worker 可启动，stdout 可读
"""

import asyncio
import json


async def main():
    print("CLIConductor Spike (Python)")

    # 启动 cbc 子进程 (Windows 需完整路径，cbc.cmd 在 node_global 目录)
    process = await asyncio.create_subprocess_exec(
        r"D:\node_npm\node_global\cbc.cmd",
        "-p",
        "--output-format", "stream-json",
        "--input-format", "stream-json",
        "-y",
        stdout=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    # 发送测试消息 (stdin stream-json 格式)
    msg = json.dumps({
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": "Say 'spike python OK' and nothing else."}]
        }
    })
    process.stdin.write((msg + "\n").encode())
    await process.stdin.drain()
    process.stdin.close()  # 告诉 cbc 没有更多输入了

    # 逐行读取 stdout
    async for line in process.stdout:
        line_str = line.decode("utf-8", errors="replace").rstrip("\n")
        if not line_str:
            continue
        try:
            event = json.loads(line_str)
        except json.JSONDecodeError:
            print(f"[RAW] {line_str[:200]}")
            continue
        t = event.get("type")
        if t == "assistant":
            content = event.get("message", {}).get("content", [])
            for block in content:
                if block.get("type") == "text":
                    print(f"[TEXT] {block['text']}")
                elif block.get("type") == "thinking":
                    print(f"[THINK] {block['thinking'][:100]}...")
        elif t == "result":
            print(f"[DONE] {event.get('subtype')}: {event.get('result')}")
            break

    process.kill()
    await process.wait()
    print("Spike completed.")


if __name__ == "__main__":
    asyncio.run(main())
