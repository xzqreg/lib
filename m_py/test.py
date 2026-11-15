import os
import json
import re

def strip_comments(text):
    """安全地移除 JSON 中的 // 注释"""
    res = []
    in_string = False
    escaped = False
    i = 0
    while i < len(text):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == '"':
                in_string = False
            res.append(ch)
        else:
            if ch == '"':
                in_string = True
                res.append(ch)
            elif ch == '/' and i + 1 < len(text) and text[i+1] == '/':
                while i < len(text) and text[i] != '\n':
                    i += 1
                if i < len(text):
                    res.append('\n')
            else:
                res.append(ch)
        i += 1
    return ''.join(res)

def main():
    json_path = 'box.json'
    
    if not os.path.exists(json_path):
        print(f"错误：找不到 {json_path} 文件！")
        return

    print("正在读取 box.json ...")
    with open(json_path, 'r', encoding='utf-8') as f:
        content = f.read()

    try:
        clean_content = strip_comments(content)
        data = json.loads(clean_content)
    except Exception as e:
        print(f"解析 JSON 失败，请检查文件格式：{e}")
        return

    # 直接清空原有的 sites 列表
    data["sites"] = []
    
    # 扫描当前目录下的所有 .py 文件
    new_sites = []
    
    for file in os.listdir('.'):
        if file.endswith(".py"):
            # 排除运行脚本和系统自带文件
            if file in ['test.py', 'update_sites.py', '__init__.py']:
                continue
            
            base_name = file[:-3]  # 去掉 .py 后缀
            
            # 生成 key：去掉特殊符号，防止播放器报错
            safe_key = re.sub(r'[^\w\u4e00-\u9fa5]', '', base_name)
            key_name = f"py_{safe_key}"
            
            api_path = f"./{file}"
            
            new_site = {
                "key": key_name,
                "name": base_name,
                "type": 3,
                "api": api_path,
                "searchable": 1,
                "quickSearch": 1,
                "filterable": 1
            }
            new_sites.append(new_site)
            print(f"收录源: {file}")

    # 将新生成的源加入 sites
    data["sites"] = new_sites

    # 备份原文件
    os.rename(json_path, json_path + ".bak")
    print(f"\n原文件已备份为 {json_path}.bak")

    # 写入更新后的数据
    with open(json_path, 'w', encoding='utf-8') as f:
        f.write("// sites 已重置为本地 py 源\n")
        json.dump(data, f, ensure_ascii=False, indent=1)
    
    print(f"✅ 替换成功！sites 已清空，现已重新编入 {len(new_sites)} 个本地 .py 源。")

if __name__ == "__main__":
    main()