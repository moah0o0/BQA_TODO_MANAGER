#!/usr/bin/env python3
"""
엑셀 파일(스케치.xlsx)에서 데이터를 읽어 데이터베이스에 임포트하는 스크립트
"""
import pandas as pd
import sqlite3
import os
import re
import random
import string
from datetime import datetime

DATABASE = 'database.db'
EXCEL_FILE = '스케치.xlsx'

# 일정 ID 매핑 (괄호 안 ID -> 생성된 ID)
schedule_id_map = {}

def generate_id():
    """4자리 랜덤 ID 생성"""
    return ''.join(random.choices(string.ascii_uppercase, k=4))

def extract_schedule_id(id_text):
    """ID 텍스트에서 실제 ID 추출 또는 생성"""
    if pd.isna(id_text):
        return generate_id()

    id_str = str(id_text).strip()

    # 괄호 안에 ID가 있는 경우 (예: "자동부여 \n(FFFF)")
    match = re.search(r'\(([A-Z]{4})\)', id_str)
    if match:
        return match.group(1)

    # 기존 ID가 없으면 새로 생성
    return generate_id()

def clear_database():
    """기존 데이터를 모두 삭제합니다."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM tasks')
    cursor.execute('DELETE FROM schedules')
    cursor.execute('DELETE FROM activists')
    conn.commit()
    conn.close()
    print("기존 데이터 삭제 완료")

def import_activists(df):
    """활동가 데이터를 임포트합니다."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    count = 0
    # 2행부터 데이터 (0-indexed로 row 2+)
    for i, row in df.iloc[2:].iterrows():
        activist_id = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else None
        name = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else None

        if activist_id and name and activist_id != 'nan':
            cursor.execute('INSERT INTO activists (id, name) VALUES (?, ?)', (activist_id, name))
            count += 1

    conn.commit()
    conn.close()
    print(f"활동가 {count}명 임포트 완료")

def import_schedules(df):
    """일정 데이터를 임포트합니다."""
    global schedule_id_map
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    count = 0
    # 3행부터 데이터 (0-indexed로 row 3+)
    for i, row in df.iloc[3:].iterrows():
        id_text = row.iloc[1]
        schedule_id = extract_schedule_id(id_text)

        # 괄호 안 ID가 있으면 매핑 저장 (실무 테이블에서 참조용)
        match = re.search(r'\(([A-Z]{4})\)', str(id_text) if pd.notna(id_text) else '')
        if match:
            schedule_id_map[match.group(1)] = schedule_id

        date_val = row.iloc[2]
        category = str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else ''
        title = str(row.iloc[4]).strip() if pd.notna(row.iloc[4]) else ''
        is_confirmed_val = row.iloc[5] if len(row) > 5 else None
        details = str(row.iloc[6]).strip() if len(row) > 6 and pd.notna(row.iloc[6]) else ''

        if not title:
            continue

        # 제목에서 줄바꿈 정리
        title = title.replace('\n', ' ').strip()

        # 날짜 처리
        date_str = ''
        if pd.notna(date_val):
            if isinstance(date_val, (pd.Timestamp, datetime)):
                date_str = date_val.strftime('%Y-%m-%d')
            elif isinstance(date_val, str):
                date_str = date_val.strip().replace('\n', ' ')

                # 이미 YYYY-MM-DD 또는 YYYY-MM 형식이면 그대로
                if re.match(r'^\d{4}-\d{2}(-\d{2})?$', date_str):
                    pass
                # "7월", "1월" -> 2026-MM
                elif re.match(r'^(\d{1,2})월$', date_str):
                    month = int(re.match(r'^(\d{1,2})월$', date_str).group(1))
                    date_str = f'2026-{month:02d}'
                # "4월 초", "3월 말", "6월 중순", "9월 중 미정" 등 -> 2026-MM-시기
                elif match := re.match(r'^(\d{1,2})월\s*(초|중순?|말)(?:\s*미정)?$', date_str):
                    month = int(match.group(1))
                    timing = match.group(2)
                    if timing in ['중', '중순']:
                        timing = '중순'
                    date_str = f'2026-{month:02d}-{timing}'
                # "5월 말~6월 초" 같은 범위
                elif match := re.match(r'^(\d{1,2})월\s*(초|중순?|말)?[~\-](\d{1,2})월\s*(초|중순?|말)?$', date_str):
                    month1 = int(match.group(1))
                    timing1 = match.group(2) or ''
                    month2 = int(match.group(3))
                    timing2 = match.group(4) or ''
                    date_str = f'2026-{month1:02d}-{timing1}~{month2:02d}-{timing2}'
                # "4월 2일(목)" 같은 특정 날짜 -> 2026-04-02
                elif match := re.match(r'^(\d{1,2})월\s*(\d{1,2})일(?:\s*\([월화수목금토일]\))?$', date_str):
                    month = int(match.group(1))
                    day = int(match.group(2))
                    date_str = f'2026-{month:02d}-{day:02d}'
                # "3월 6일(금) 또는 7일(토)" 같은 복잡한 형식 -> 대략적으로 처리
                elif match := re.match(r'^(\d{1,2})월\s*(\d{1,2})일', date_str):
                    month = int(match.group(1))
                    day = int(match.group(2))
                    # 원본 텍스트를 details에 보존
                    original_text = date_str
                    date_str = f'2026-{month:02d}-{day:02d}'
                    details = f"[일정 참고: {original_text}]\n{details}" if details else f"[일정 참고: {original_text}]"
                # "5월 17일(일)까지" 같은 형식
                elif match := re.match(r'^(\d{1,2})월\s*(\d{1,2})일(?:\s*\([월화수목금토일]\))?(?:까지|부터)?$', date_str):
                    month = int(match.group(1))
                    day = int(match.group(2))
                    date_str = f'2026-{month:02d}-{day:02d}'
                # "미정"
                elif date_str == '미정':
                    date_str = ''
                # "연중 1회", "연중" 등
                elif re.match(r'^연중', date_str):
                    date_str = '연중'
                # 그 외 복잡한 형식은 그대로 보존
                else:
                    # 월 정보라도 추출 시도
                    month_only = re.search(r'(\d{1,2})월', date_str)
                    if month_only:
                        month = int(month_only.group(1))
                        # 원본 텍스트 보존하면서 정렬용 월 정보 사용
                        original_text = date_str
                        date_str = f'2026-{month:02d}-미정'
                        details = f"[일정 참고: {original_text}]\n{details}" if details else f"[일정 참고: {original_text}]"
                    else:
                        date_str = ''

        # 확정 여부 처리
        is_confirmed = 0
        if pd.notna(is_confirmed_val):
            if isinstance(is_confirmed_val, bool):
                is_confirmed = 1 if is_confirmed_val else 0
            elif isinstance(is_confirmed_val, (int, float)):
                is_confirmed = 1 if is_confirmed_val == 1 else 0
            elif isinstance(is_confirmed_val, str):
                is_confirmed = 1 if is_confirmed_val.strip().lower() in ['1', 'true', 'o', '확정'] else 0

        cursor.execute('''
            INSERT INTO schedules (id, date, category, title, is_confirmed, is_completed, details)
            VALUES (?, ?, ?, ?, ?, 0, ?)
        ''', (schedule_id, date_str, category, title, is_confirmed, details))
        count += 1

    conn.commit()
    conn.close()
    print(f"일정 {count}건 임포트 완료")
    print(f"ID 매핑: {schedule_id_map}")

def import_tasks(df):
    """실무 데이터를 임포트합니다."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    count = 0
    # 2행부터 데이터 (0-indexed로 row 2+)
    for i, row in df.iloc[2:].iterrows():
        schedule_id_text = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else None

        if not schedule_id_text:
            continue

        # 괄호 제거하여 ID 추출 (예: "(FFFF)" -> "FFFF")
        schedule_id = re.sub(r'[()]', '', schedule_id_text)

        # ID 매핑에서 실제 ID 찾기
        if schedule_id in schedule_id_map:
            schedule_id = schedule_id_map[schedule_id]

        priority_val = row.iloc[2]
        priority = int(priority_val) if pd.notna(priority_val) and isinstance(priority_val, (int, float)) else 1

        activist_id = str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else None
        is_idea_val = row.iloc[4] if len(row) > 4 else None
        deadline_val = row.iloc[5] if len(row) > 5 else None
        content = str(row.iloc[6]).strip() if len(row) > 6 and pd.notna(row.iloc[6]) else ''

        if not content:
            continue

        # 아이디어 여부 처리
        is_idea = 0
        if pd.notna(is_idea_val):
            if isinstance(is_idea_val, bool):
                is_idea = 1 if is_idea_val else 0
            elif isinstance(is_idea_val, (int, float)):
                is_idea = 1 if is_idea_val == 1 else 0
            elif isinstance(is_idea_val, str):
                is_idea = 1 if is_idea_val.strip().lower() in ['1', 'true', 'o'] else 0

        # 마감일 처리
        deadline = ''
        if pd.notna(deadline_val):
            if isinstance(deadline_val, (pd.Timestamp, datetime)):
                deadline = deadline_val.strftime('%Y-%m-%d')
            elif isinstance(deadline_val, str):
                deadline_str = deadline_val.strip()
                # "4월" 같은 월만 있는 경우 -> 2026-04 형식으로
                month_match = re.match(r'^(\d{1,2})월$', deadline_str)
                if month_match:
                    month = int(month_match.group(1))
                    deadline = f'2026-{month:02d}'
                else:
                    deadline = deadline_str

        # activist_id가 빈 문자열이면 None으로
        if activist_id == '' or activist_id == 'nan':
            activist_id = None

        cursor.execute('''
            INSERT INTO tasks (schedule_id, priority, activist_id, is_idea, is_draft, deadline, content, is_completed)
            VALUES (?, ?, ?, ?, 0, ?, ?, 0)
        ''', (schedule_id, priority, activist_id, is_idea, deadline, content))
        count += 1

    conn.commit()
    conn.close()
    print(f"실무 {count}건 임포트 완료")

def main():
    if not os.path.exists(EXCEL_FILE):
        print(f"오류: {EXCEL_FILE} 파일을 찾을 수 없습니다.")
        return

    print(f"\n=== {EXCEL_FILE} 데이터 임포트 시작 ===\n")

    # 엑셀 파일 읽기
    xlsx = pd.ExcelFile(EXCEL_FILE)
    print(f"시트 목록: {xlsx.sheet_names}")

    # 기존 데이터 삭제
    clear_database()

    # 활동가 임포트 (header=None으로 읽기)
    if '활동가' in xlsx.sheet_names:
        df_activists = pd.read_excel(xlsx, sheet_name='활동가', header=None)
        print(f"\n[활동가] {len(df_activists)}행 (헤더 제외 {len(df_activists) - 2}건)")
        import_activists(df_activists)

    # 일정 임포트 (header=None으로 읽기)
    if '주요 일정표' in xlsx.sheet_names:
        df_schedules = pd.read_excel(xlsx, sheet_name='주요 일정표', header=None)
        print(f"\n[주요 일정표] {len(df_schedules)}행 (헤더 제외 {len(df_schedules) - 3}건)")
        import_schedules(df_schedules)

    # 실무 임포트 (header=None으로 읽기)
    if '주요 실무표' in xlsx.sheet_names:
        df_tasks = pd.read_excel(xlsx, sheet_name='주요 실무표', header=None)
        print(f"\n[주요 실무표] {len(df_tasks)}행 (헤더 제외 {len(df_tasks) - 2}건)")
        import_tasks(df_tasks)

    print("\n=== 임포트 완료 ===")

    # 결과 확인
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM activists')
    print(f"활동가: {cursor.fetchone()[0]}명")

    cursor.execute('SELECT COUNT(*) FROM schedules')
    print(f"일정: {cursor.fetchone()[0]}건")

    cursor.execute('SELECT COUNT(*) FROM tasks')
    print(f"실무: {cursor.fetchone()[0]}건")

    # 샘플 데이터 출력
    print("\n--- 활동가 목록 ---")
    cursor.execute('SELECT * FROM activists')
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]}")

    print("\n--- 일정 샘플 (처음 5건) ---")
    cursor.execute('SELECT id, date, category, title FROM schedules LIMIT 5')
    for row in cursor.fetchall():
        print(f"  [{row[0]}] {row[1] or '미정'} | {row[2]} | {row[3][:30]}...")

    print("\n--- 실무 샘플 (처음 5건) ---")
    cursor.execute('SELECT schedule_id, activist_id, deadline, content FROM tasks LIMIT 5')
    for row in cursor.fetchall():
        print(f"  [{row[0]}] 담당:{row[1] or '-'} | 마감:{row[2] or '-'} | {row[3][:30]}...")

    conn.close()

if __name__ == '__main__':
    main()
