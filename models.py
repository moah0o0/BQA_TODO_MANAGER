import sqlite3
from datetime import datetime
import os

DATABASE = os.environ.get('DATABASE_PATH', 'database.db')

def get_db():
    """데이터베이스 연결을 반환합니다."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """데이터베이스 테이블을 생성합니다."""
    conn = get_db()
    cursor = conn.cursor()

    # 활동가 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activists (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL
        )
    ''')

    # 주요 일정표 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS schedules (
            id TEXT PRIMARY KEY,
            date TEXT,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            is_confirmed INTEGER DEFAULT 0,
            is_completed INTEGER DEFAULT 0,
            details TEXT
        )
    ''')

    # 실무/TODO 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule_id TEXT NOT NULL,
            priority INTEGER DEFAULT 1,
            activist_id TEXT,
            is_idea INTEGER DEFAULT 0,
            is_draft INTEGER DEFAULT 0,
            deadline TEXT,
            content TEXT NOT NULL,
            is_completed INTEGER DEFAULT 0,
            FOREIGN KEY (schedule_id) REFERENCES schedules(id),
            FOREIGN KEY (activist_id) REFERENCES activists(id)
        )
    ''')

    # is_draft 컬럼이 없으면 추가 (기존 DB 호환)
    try:
        cursor.execute('ALTER TABLE tasks ADD COLUMN is_draft INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass  # 컬럼이 이미 존재함

    # created_at 컬럼 추가 (기존 DB 호환)
    try:
        cursor.execute('ALTER TABLE tasks ADD COLUMN created_at TEXT')
    except sqlite3.OperationalError:
        pass  # 컬럼이 이미 존재함

    # 사업 아이디어 테이블 (일정과 무관한 아이디어)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ideas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            activist_id TEXT,
            is_adopted INTEGER DEFAULT 0,
            created_at TEXT,
            FOREIGN KEY (activist_id) REFERENCES activists(id)
        )
    ''')

    conn.commit()
    conn.close()

def seed_initial_data():
    """초기 데이터를 삽입합니다."""
    conn = get_db()
    cursor = conn.cursor()

    # 이미 데이터가 있는지 확인
    cursor.execute('SELECT COUNT(*) FROM activists')
    if cursor.fetchone()[0] > 0:
        conn.close()
        return

    # 활동가 데이터
    activists = [
        ('A', '김찬'),
        ('B', '김은해'),
        ('C', '교1'),
    ]
    cursor.executemany('INSERT INTO activists (id, name) VALUES (?, ?)', activists)

    # 주요 일정 데이터 (일부)
    schedules = [
        ('FFFF', '2026-02-28', '정기모임', '세상을 향해 목소리내는 집회 가기 전에 잠깐만?', 1, 0,
         '''(1) 영화 시청 - <빵과 장미>(1시간 50분)
(2) 요약발제 - "빵과 장미"의 과거와 현재 (25분)
(3) 3.8 여성대회 참여방식에 대한 준비를 회원들과 함께 한다. (40분)'''),
        ('CCCC', '2026-03-21', '정기모임', '퀴어생활맞춤형 원데이클래스', 0, 0,
         '(1) 퀴어들이 한국사회에서 살아가며 필요한 지식 배우기 (2시간)'),
        ('DDDD', '2026-05-01', '정기모임 연계활동', '5·1 세계노동절 부산대회', 0, 0, '미정'),
        ('EEEE', '2026-03', '연대사업', '민주노총 부산본부 청년라운드테이블', 1, 0,
         '민주노총 부산본부 청년 조합원들과 지역사회 청년들이 모여 지방선거 의제를 토론한다.'),
        ('GGGG', '2026-04-02', '연대사업', '노동법 무료시민강좌 회원 참여 독려', 1, 0,
         '민주노총 부산본부 시민강좌 1강 (2인 이상의 회원이 대화를 나누고, 후기 나누기 활동)'),
    ]
    cursor.executemany('''
        INSERT INTO schedules (id, date, category, title, is_confirmed, is_completed, details)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', schedules)

    # 실무 데이터 (일부)
    tasks = [
        ('FFFF', 1, 'A', 0, '2026-02-02', '교육 PPT 제작 - 영상 및 사진 위주로', 0),
        ('FFFF', 2, 'B', 0, '2026-02-03', '장소 대관', 0),
        ('FFFF', 3, 'C', 0, '2026-02-04', '영화 파일 확보', 0),
        ('CCCC', 1, 'A', 0, '2026-02-02', '원데이클래스 주제 선정', 0),
        ('DDDD', 1, 'B', 1, '2026-04', '원데이클래스 주제 선정 (아이디어)', 0),
    ]
    cursor.executemany('''
        INSERT INTO tasks (schedule_id, priority, activist_id, is_idea, deadline, content, is_completed)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', tasks)

    conn.commit()
    conn.close()

def generate_schedule_id():
    """새로운 일정 ID를 생성합니다."""
    import random
    import string
    return ''.join(random.choices(string.ascii_uppercase, k=4))

if __name__ == '__main__':
    init_db()
    seed_initial_data()
    print("데이터베이스가 초기화되었습니다.")
