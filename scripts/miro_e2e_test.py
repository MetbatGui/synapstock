import os
import json
from dotenv import load_dotenv
from synapstock.adapters.miro.miro_mindmap import MiroMindmapAdapter
from synapstock.domain.models import Board, Node, Stock

def load_it_json(path: str) -> Board:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    board_name = data.get("name", "IT")
    root_data = data.get("root", {})
    
    def parse_node(n_data: dict, depth: int) -> Node:
        node = Node(name=n_data.get("name", ""), depth=depth)
        for child_data in n_data.get("nodes", []):
            node.nodes.append(parse_node(child_data, depth + 1))
        for s_data in n_data.get("stocks", []):
            node.stocks.append(Stock(name=s_data.get("name", ""), ticker=s_data.get("ticker", "")))
        return node
    
    board = Board(name=board_name)
    board.root = parse_node(root_data, 0)
    return board

def run_e2e():
    load_dotenv()
    token = os.getenv("MIRO_ACCESS_TOKEN")
    if not token:
        print("MIRO_ACCESS_TOKEN not found in .env")
        return

    # 1. 새 보드 생성
    import requests
    import time
    timestamp = str(int(time.time()))
    new_board_name = f"IT Theme Test Board {timestamp}"
    res = requests.post(
        "https://api.miro.com/v2/boards", 
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"name": new_board_name}
    )
    if not res.ok:
        print(f"Failed to create new board: {res.text}")
        return
    board_data = res.json()
    board_view_url = board_data.get("viewLink", f"https://miro.com/app/board/{board_data['id']}/")
    print(f"New board created: {new_board_name}")
    print(f"Board Link: {board_view_url}")

    # 2. IT.json 로드
    it_json_path = os.path.join("tests", "fixtures", "boards", "IT.json")
    if not os.path.exists(it_json_path):
        print(f"File not found: {it_json_path}")
        return
    
    print(f"Loading {it_json_path}...")
    board = load_it_json(it_json_path)
    
    # 보드 이름을 방금 생성한 새 보드 이름으로 부여
    board.name = new_board_name
    
    adapter = MiroMindmapAdapter(api_token=token)
    
    # 3. Miro에 저장
    print(f"Saving '{board.name}' to Miro...")
    adapter.save(board)
    print("Save completed.")

    # 3. 다시 로드하여 확인
    print(f"Loading '{board.name}' from Miro...")
    reloaded_board = adapter.load(board.name)
    print(f"Loaded board: {reloaded_board.name}")
    print(f"Root name: {reloaded_board.root.name}")
    print(f"Total Top Nodes: {len(reloaded_board.root.nodes)}")
    
    # 4. 증분 업데이트 테스트 (노드 하나 추가)
    print("Testing incremental update (Reconciliation)...")
    new_node = Node(name="Test Incremental Node", depth=1)
    board.root.nodes.append(new_node)
    adapter.save(board)
    print("Incremental save completed.")

if __name__ == "__main__":
    run_e2e()
