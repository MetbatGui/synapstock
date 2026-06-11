import json
from pathlib import Path

def cleanup_dummy_listings():
    # 1. 파일 경로 설정
    base_dir = Path(__file__).resolve().parents[1]
    virtual_board_path = base_dir / "data" / "board" / "virtual_신규상장주.json"
    manifest_path = base_dir / "data" / "board" / "board_sync_manifest.json"

    print("=== 신규상장주 더미 데이터 클린업 마이그레이션 시작 ===")

    # 2. 가상보드 클린업
    if virtual_board_path.exists():
        try:
            board_data = json.loads(virtual_board_path.read_text(encoding="utf-8"))
            stocks = board_data.get("root", {}).get("stocks", [])
            initial_count = len(stocks)
            
            # 티커가 '99'로 시작하거나 종목명에 '더미'가 포함된 경우 제외
            cleaned_stocks = [
                s for s in stocks 
                if not (s.get("ticker", "").startswith("99") or "더미" in s.get("name", ""))
            ]
            removed_count = initial_count - len(cleaned_stocks)
            
            board_data["root"]["stocks"] = cleaned_stocks
            virtual_board_path.write_text(json.dumps(board_data, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"[가상보드] 청소 완료 (총 {initial_count}개 중 {removed_count}개 더미 제거, 남은 종목: {len(cleaned_stocks)}개)")
        except Exception as e:
            print(f"[가상보드] 오류 발생: {e}")
    else:
        print("[가상보드] 파일이 존재하지 않아 스킵합니다.")

    # 3. 통합 매니페스트 클린업
    if manifest_path.exists():
        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            new_listings = manifest_data.get("new_listings", {})
            initial_count = len(new_listings)
            
            # 티커(key)가 '99'로 시작하거나 종목명에 '더미'가 포함된 경우 제외
            cleaned_listings = {
                ticker: info for ticker, info in new_listings.items()
                if not (ticker.startswith("99") or "더미" in info.get("name", ""))
            }
            removed_count = initial_count - len(cleaned_listings)
            
            manifest_data["new_listings"] = cleaned_listings
            manifest_path.write_text(json.dumps(manifest_data, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"[매니페스트] 청소 완료 (총 {initial_count}개 중 {removed_count}개 더미 제거, 남은 종목: {len(cleaned_listings)}개)")
        except Exception as e:
            print(f"[매니페스트] 오류 발생: {e}")
    else:
        print("[매니페스트] 파일이 존재하지 않아 스킵합니다.")

    # 4. 기존 꼬여있던 로컬 캐시 파일들 일괄 제거 (스마트 캐싱 최초 동기화 정합성 확보)
    cache_dir = base_dir / "data" / "statistics" / "new_listing"
    if cache_dir.exists():
        deleted_caches = []
        for p in cache_dir.glob("new_listing_data_*.json"):
            try:
                p.unlink()
                deleted_caches.append(p.name)
            except Exception as e:
                print(f"[캐시 파일 삭제 실패] {p.name}: {e}")
        if deleted_caches:
            print(f"[로컬 캐시 초기화] 기존 캐시 파일 삭제 완료: {', '.join(deleted_caches)}")
    
    print("=== 클린업 마이그레이션 완료 ===")

if __name__ == "__main__":
    cleanup_dummy_listings()
