import json

def split_binary_by_map(binary_data, map_data):
    """
    根據 map.json 區段描述，將 binary 資料分段，回傳每段資料與對應 metadata。
    每個區段會回傳字典包含:
      - "handler": 區段使用的處理器
      - "meta": metadata，包含 offset, size, target, 等欄位
      - "data": binary 子資料
    """
    sections = []

    for idx, entry in enumerate(map_data):
        offset = entry.get("offset")
        size = entry.get("size")
        handler = entry.get("handler", "default")  # 預設 handler 為 default
        target = entry.get("target", 0)

        if offset is None or size is None:
            raise ValueError(f"Invalid map entry at index {idx}: 'offset' or 'size' missing")

        data = binary_data[offset : offset + size]
        if len(data) != size:
            raise ValueError(f"Binary data too short for section {idx}: expected {size} bytes, got {len(data)}")

        section = {
            "handler": handler,
            "meta": {
                "offset": offset,
                "size": size,
                "target": target
            },
            "data": data
        }

        sections.append(section)

    return sections

