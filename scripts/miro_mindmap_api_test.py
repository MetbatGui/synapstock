import os
import requests
from dotenv import load_dotenv

def test_mindmap_api():
    load_dotenv()
    token = os.getenv("MIRO_ACCESS_TOKEN")
    if not token:
        print("MIRO_ACCESS_TOKEN not found in .env")
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    base_url = "https://api.miro.com/v2"
    experimental_base_url = "https://api.miro.com/v2-experimental"

    print("1. 새 보드 생성...")
    board_payload = {"name": "Mindmap API Test (Auto Layout - 13 Nodes)"}
    res = requests.post(f"{base_url}/boards", headers=headers, json=board_payload)
    if not res.ok:
        print(f"Failed to create board: {res.status_code} {res.text}")
        return
    board_id = res.json()["id"]
    board_view_url = res.json().get("viewLink", f"https://miro.com/app/board/{board_id}/")
    print(f"새 보드 생성 성공! 링크: {board_view_url}")

    api_url = f"{experimental_base_url}/boards/{board_id}/mindmap_nodes"

    print("\n2. 마인드맵 루트 노드(1개) 생성 시도...")
    root_payload = {"data": {"nodeView": {"data": {"content": "중앙 노드 (Root)"}}}}
    res = requests.post(api_url, headers=headers, json=root_payload)
    if not res.ok:
        print(f"루트 노드 생성 실패: {res.status_code} {res.text}")
        return
    root_node_id = res.json()["id"]
    print(f"루트 노드 생성 성공! ID: {root_node_id}")

    print("\n3. 자식 마인드맵 노드(서브 노드 3개) 생성...")
    sub_ids = []
    for i in range(1, 4):
        child_payload = {
            "data": {"nodeView": {"data": {"content": f"서브 노드 {i}"}}},
            "parent": {"id": root_node_id} # position 생략! (마구잡이 때려넣기 자동 레이아웃)
        }
        res_sub = requests.post(api_url, headers=headers, json=child_payload)
        if res_sub.ok:
            sub_id = res_sub.json()["id"]
            sub_ids.append(sub_id)
            print(f"서브 노드 {i} 생성 성공! ID: {sub_id}")
        else:
            print(f"서브 노드 {i} 생성 오류: {res_sub.status_code} {res_sub.text}")

    print(f"\n4. 카드(종목) 노드 생성 시도 (각 서브노드 당 3개씩, 총 9개)...")
    for i, sub_id in enumerate(sub_ids, 1):
        for j in range(1, 4):
            card_content = f"[\ud0c0\uc774\ud2c0]<br/>\uc774\ub984: \uc885\ubaa9 {i}-{j}<br/>ticker: 000{i}{j}0"
            card_payload = {
                "data": {"nodeView": {"data": {"content": card_content}}},
                "parent": {"id": sub_id} # position 생략!
            }
                
            res_card = requests.post(api_url, headers=headers, json=card_payload)
            if res_card.ok:
                print(f"자식 노드(카드 역할) {i}-{j} 생성 성공!")
            else:
                print(f"자식 노드 {i}-{j} 생성 오류: {res_card.status_code} {res_card.text}")

    print(f"\n완료! 보드 링크를 열어 확인해보세요: {board_view_url}")

if __name__ == "__main__":
    test_mindmap_api()
