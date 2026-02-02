import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from datetime import datetime, timedelta, timezone
from models import get_db, init_db, seed_initial_data, generate_schedule_id, User
from authlib.integrations.flask_client import OAuth
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from functools import wraps

# 한국 시간대 (KST = UTC+9)
KST = timezone(timedelta(hours=9))

def get_kst_now():
    """현재 한국 시간을 반환합니다."""
    return datetime.now(KST)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'busan-queer-action-2026-dev')

# Flask-Login 설정
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = '로그인이 필요합니다.'

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

# OAuth 설정
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID'),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

def approval_required(f):
    """승인된 사용자만 접근 가능하도록 하는 데코레이터"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        if not current_user.is_active():
            flash('관리자의 승인이 필요합니다.')
            return redirect(url_for('pending_approval'))
        return f(*args, **kwargs)
    return decorated_function

# 앱 시작 시 DB 초기화
with app.app_context():
    init_db()
    seed_initial_data()


def parse_date(date_str):
    """날짜 문자열을 파싱합니다. 대략적 시기도 정렬용으로 변환합니다."""
    import re
    if not date_str:
        return None

    # YYYY-MM-DD (정확한 날짜)
    try:
        return datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        pass

    # YYYY-MM (월만) -> 15일로 설정
    try:
        return datetime.strptime(date_str + '-15', '%Y-%m-%d')
    except ValueError:
        pass

    # YYYY-MM-초/중순/말/미정 (대략적 시기)
    match = re.match(r'^(\d{4})-(\d{2})-(초|중순|말|미정)$', date_str)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        timing = match.group(3)
        # 초: 5일, 중순: 15일, 말: 25일, 미정: 15일
        day_map = {'초': 5, '중순': 15, '말': 25, '미정': 15}
        day = day_map.get(timing, 15)
        return datetime(year, month, day)

    # YYYY-MM-시기~MM-시기 (범위) -> 첫 번째 월 기준
    match = re.match(r'^(\d{4})-(\d{2})-(초|중순|말)?~', date_str)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        timing = match.group(3) or '중순'
        day_map = {'초': 5, '중순': 15, '말': 25}
        day = day_map.get(timing, 15)
        return datetime(year, month, day)

    # "연중" -> 연말(12월)로 정렬
    if date_str == '연중':
        return datetime(2026, 12, 31)

    return None


def calc_dday(deadline_str):
    """D-day를 계산합니다. 반환: (일수, CSS클래스)"""
    if not deadline_str:
        return None, 'safe'

    deadline = parse_date(deadline_str)
    if not deadline:
        return None, 'safe'

    # 타임존 없는 날짜로 비교 (날짜만 비교하면 되므로)
    today = get_kst_now().replace(tzinfo=None)
    today = today.replace(hour=0, minute=0, second=0, microsecond=0)
    diff = (deadline - today).days

    if diff < 0:
        return f'D+{abs(diff)}', 'overdue'
    elif diff == 0:
        return 'D-Day', 'd1'
    elif diff == 1:
        return 'D-1', 'd1'
    elif diff == 2:
        return 'D-2', 'd2'
    elif diff == 3:
        return 'D-3', 'd3'
    else:
        return f'D-{diff}', 'safe'


def format_date_kr(date_str):
    """날짜를 한국어 형식으로 변환합니다."""
    import re
    if not date_str:
        return '미정'

    # "연중"
    if date_str == '연중':
        return '연중 1회'

    # YYYY-MM-DD (정확한 날짜)
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        dt = parse_date(date_str)
        if dt:
            return dt.strftime('%m월 %d일')

    # YYYY-MM (월만)
    if re.match(r'^\d{4}-\d{2}$', date_str):
        try:
            month = int(date_str[5:7])
            return f'{month}월'
        except ValueError:
            pass

    # YYYY-MM-초/중순/말/미정 (대략적 시기)
    match = re.match(r'^(\d{4})-(\d{2})-(초|중순|말|미정)$', date_str)
    if match:
        month = int(match.group(2))
        timing = match.group(3)
        return f'{month}월 {timing}'

    # YYYY-MM-시기~MM-시기 (범위)
    match = re.match(r'^(\d{4})-(\d{2})-(초|중순|말)?~(\d{2})-(초|중순|말)?$', date_str)
    if match:
        month1 = int(match.group(2))
        timing1 = match.group(3) or ''
        month2 = int(match.group(4))
        timing2 = match.group(5) or ''
        return f'{month1}월 {timing1}~{month2}월 {timing2}'.strip()

    # 그 외
    dt = parse_date(date_str)
    if dt:
        return dt.strftime('%m월 %d일')
    return date_str


# Jinja2 필터 등록
app.jinja_env.filters['dday'] = lambda d: calc_dday(d)[0]
app.jinja_env.filters['dday_class'] = lambda d: calc_dday(d)[1]
app.jinja_env.filters['date_kr'] = format_date_kr


# ========== 인증 ==========

@app.route('/login')
def login():
    """로그인 페이지"""
    if current_user.is_authenticated:
        if current_user.is_active():
            return redirect(url_for('index'))
        return redirect(url_for('pending_approval'))
    return render_template('login.html')


@app.route('/login/google')
def login_google():
    """Google OAuth 로그인 시작"""
    redirect_uri = url_for('auth_callback', _external=True)
    return google.authorize_redirect(redirect_uri)


@app.route('/auth/callback')
def auth_callback():
    """Google OAuth 콜백"""
    try:
        token = google.authorize_access_token()
        user_info = token.get('userinfo')

        if not user_info:
            flash('Google 로그인에 실패했습니다.')
            return redirect(url_for('login'))

        google_id = user_info.get('sub')
        email = user_info.get('email')
        name = user_info.get('name')
        picture = user_info.get('picture')

        # 기존 사용자 확인
        user = User.get_by_google_id(google_id)

        if not user:
            # 새 사용자 생성
            conn = get_db()
            cursor = conn.cursor()

            # 첫 번째 사용자인지 확인 (자동 승인)
            cursor.execute('SELECT COUNT(*) FROM users')
            is_first_user = cursor.fetchone()[0] == 0
            is_approved = 1 if is_first_user else 0

            created_at = get_kst_now().strftime('%Y-%m-%d %H:%M')
            cursor.execute('''
                INSERT INTO users (google_id, email, name, picture, is_approved, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (google_id, email, name, picture, is_approved, created_at))
            conn.commit()
            user_id = cursor.lastrowid
            conn.close()

            user = User(user_id, google_id, email, name, picture, is_approved)
            if is_first_user:
                flash('첫 번째 사용자로 자동 승인되었습니다!')
            else:
                flash('가입이 완료되었습니다. 관리자 승인을 기다려주세요.')

        login_user(user)

        if user.is_active():
            return redirect(url_for('index'))
        return redirect(url_for('pending_approval'))

    except Exception as e:
        flash(f'로그인 중 오류가 발생했습니다: {str(e)}')
        return redirect(url_for('login'))


@app.route('/logout')
@login_required
def logout():
    """로그아웃"""
    logout_user()
    flash('로그아웃되었습니다.')
    return redirect(url_for('login'))


@app.route('/pending')
@login_required
def pending_approval():
    """승인 대기 페이지"""
    if current_user.is_active():
        return redirect(url_for('index'))
    return render_template('pending.html')


@app.route('/admin/users')
@approval_required
def admin_users():
    """사용자 관리 (관리자용)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users ORDER BY created_at DESC')
    users = cursor.fetchall()
    conn.close()
    return render_template('admin_users.html', users=users)


@app.route('/admin/user/<int:user_id>/approve', methods=['POST'])
@approval_required
def admin_approve_user(user_id):
    """사용자 승인"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_approved = 1 WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    flash('사용자가 승인되었습니다.')
    return redirect(url_for('admin_users'))


@app.route('/admin/user/<int:user_id>/revoke', methods=['POST'])
@approval_required
def admin_revoke_user(user_id):
    """사용자 승인 취소"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_approved = 0 WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    flash('사용자 승인이 취소되었습니다.')
    return redirect(url_for('admin_users'))


@app.route('/')
@approval_required
def index():
    """대시보드"""
    conn = get_db()
    cursor = conn.cursor()
    today = get_kst_now().replace(tzinfo=None)

    # 전체 미완료 실무 (is_idea=0)
    cursor.execute('''
        SELECT t.*, s.title as schedule_title, a.name as activist_name
        FROM tasks t
        LEFT JOIN schedules s ON t.schedule_id = s.id
        LEFT JOIN activists a ON t.activist_id = a.id
        WHERE t.is_idea = 0 AND t.is_completed = 0
        ORDER BY t.deadline ASC
    ''')
    all_tasks = cursor.fetchall()

    # D-day 계산 및 분류
    urgent_tasks = []  # D-3 이내
    week_tasks = []    # 이번 주

    for task in all_tasks:
        dday_text, dday_class = calc_dday(task['deadline'])
        task_dict = dict(task)
        task_dict['dday_text'] = dday_text
        task_dict['dday_class'] = dday_class

        deadline = parse_date(task['deadline'])
        if deadline:
            diff = (deadline - today).days
            if diff <= 3:
                urgent_tasks.append(task_dict)
            if diff <= 7:
                week_tasks.append(task_dict)

    # 통계
    stats = {
        'urgent': len(urgent_tasks),
        'week': len(week_tasks),
        'total': len(all_tasks)
    }

    # 다가오는 일정 (미완료, 2달 이내)
    two_months_later = (today + timedelta(days=60)).strftime('%Y-%m-%d')
    cursor.execute('''
        SELECT s.*,
               COUNT(t.id) as task_count,
               SUM(CASE WHEN t.is_completed = 1 THEN 1 ELSE 0 END) as completed_count
        FROM schedules s
        LEFT JOIN tasks t ON s.id = t.schedule_id AND t.is_idea = 0
        WHERE s.is_completed = 0 AND (s.date <= ? OR s.date IS NULL OR s.date = '')
        GROUP BY s.id
        ORDER BY s.date ASC
    ''', (two_months_later,))
    upcoming_schedules = cursor.fetchall()

    conn.close()

    return render_template('index.html',
                           urgent_tasks=urgent_tasks,
                           stats=stats,
                           upcoming_schedules=upcoming_schedules,
                           today=today)


# ========== 일정 관리 ==========

@app.route('/meeting')
@approval_required
def meeting():
    """회의용 뷰 - 30일 기준으로 일정과 실무 정리"""
    conn = get_db()
    cursor = conn.cursor()
    today = get_kst_now()
    today_str = today.strftime('%Y-%m-%d')
    thirty_days_later = (today + timedelta(days=30)).strftime('%Y-%m-%d')

    # 1. 30일 이내 일정 (미완료)
    cursor.execute('''
        SELECT s.*,
               COUNT(t.id) as task_count,
               SUM(CASE WHEN t.is_completed = 1 THEN 1 ELSE 0 END) as completed_count
        FROM schedules s
        LEFT JOIN tasks t ON s.id = t.schedule_id AND t.is_idea = 0
        WHERE s.is_completed = 0 AND s.date <= ? AND s.date >= ?
        GROUP BY s.id
        ORDER BY s.date ASC
    ''', (thirty_days_later, today_str))
    upcoming_schedules = cursor.fetchall()

    # 각 일정의 실무 목록 가져오기
    upcoming_with_tasks = []
    for schedule in upcoming_schedules:
        cursor.execute('''
            SELECT t.*, a.name as activist_name
            FROM tasks t
            LEFT JOIN activists a ON t.activist_id = a.id
            WHERE t.schedule_id = ? AND t.is_idea = 0
            ORDER BY t.is_completed ASC, t.deadline ASC
        ''', (schedule['id'],))
        tasks = cursor.fetchall()

        tasks_with_dday = []
        for task in tasks:
            task_dict = dict(task)
            dday_text, dday_class = calc_dday(task['deadline'])
            task_dict['dday_text'] = dday_text
            task_dict['dday_class'] = dday_class
            tasks_with_dday.append(task_dict)

        upcoming_with_tasks.append({
            'schedule': dict(schedule),
            'tasks': tasks_with_dday
        })

    # 2. 30일 이후 일정 중 마감일이 30일 이내인 실무 (일정별로 그룹화)
    # 먼저 해당 조건에 맞는 일정 목록 조회
    cursor.execute('''
        SELECT DISTINCT s.id, s.title, s.date, s.category, s.is_confirmed
        FROM schedules s
        JOIN tasks t ON s.id = t.schedule_id
        WHERE s.is_completed = 0 AND s.date > ? AND t.is_idea = 0 AND t.is_completed = 0
              AND t.deadline <= ? AND t.deadline >= ?
        ORDER BY s.date ASC
    ''', (thirty_days_later, thirty_days_later, today_str))
    future_schedules = cursor.fetchall()

    # 각 일정의 마감 임박 실무 목록 가져오기
    future_schedules_with_tasks = []
    future_tasks_with_dday = []  # 기존 호환성을 위해 유지
    for schedule in future_schedules:
        cursor.execute('''
            SELECT t.*, a.name as activist_name
            FROM tasks t
            LEFT JOIN activists a ON t.activist_id = a.id
            WHERE t.schedule_id = ? AND t.is_idea = 0 AND t.is_completed = 0
                  AND t.deadline <= ? AND t.deadline >= ?
            ORDER BY t.deadline ASC
        ''', (schedule['id'], thirty_days_later, today_str))
        tasks = cursor.fetchall()

        tasks_with_dday = []
        for task in tasks:
            task_dict = dict(task)
            task_dict['schedule_id'] = schedule['id']
            task_dict['schedule_title'] = schedule['title']
            task_dict['schedule_date'] = schedule['date']
            task_dict['schedule_category'] = schedule['category']
            dday_text, dday_class = calc_dday(task['deadline'])
            task_dict['dday_text'] = dday_text
            task_dict['dday_class'] = dday_class
            tasks_with_dday.append(task_dict)
            future_tasks_with_dday.append(task_dict)  # 기존 호환성

        schedule_dict = dict(schedule)
        dday_text, dday_class = calc_dday(schedule['date'])
        schedule_dict['dday_text'] = dday_text
        schedule_dict['dday_class'] = dday_class
        schedule_dict['tasks'] = tasks_with_dday
        future_schedules_with_tasks.append(schedule_dict)

    # 활동가 목록 (편집용)
    cursor.execute('SELECT * FROM activists')
    activists = cursor.fetchall()

    # 연중 일정 조회
    cursor.execute('''
        SELECT s.*, COUNT(t.id) as task_count
        FROM schedules s
        LEFT JOIN tasks t ON s.id = t.schedule_id AND t.is_idea = 0
        WHERE s.date = '연중' AND s.is_completed = 0
        GROUP BY s.id
    ''')
    yearly_schedules = cursor.fetchall()

    conn.close()

    # 일정에 D-day 및 태스크 정보 추가
    upcoming_schedules_result = []
    for item in upcoming_with_tasks:
        schedule = item['schedule']
        dday_text, dday_class = calc_dday(schedule['date'])
        schedule['dday_text'] = dday_text
        schedule['dday_class'] = dday_class
        schedule['tasks'] = item['tasks']
        upcoming_schedules_result.append(schedule)

    return render_template('meeting.html',
                           upcoming_schedules=upcoming_schedules_result,
                           future_schedules=future_schedules_with_tasks,
                           future_tasks=future_tasks_with_dday,
                           yearly_schedules=yearly_schedules,
                           activists=activists,
                           today_str=today.strftime('%m월 %d일'),
                           thirty_days_later=thirty_days_later)


@app.route('/schedules')
@approval_required
def schedules():
    """일정 목록"""
    conn = get_db()
    cursor = conn.cursor()

    status = request.args.get('status', 'upcoming')

    # 진행률 포함 쿼리
    base_query = '''
        SELECT s.*,
               COUNT(t.id) as task_count,
               SUM(CASE WHEN t.is_completed = 1 THEN 1 ELSE 0 END) as completed_count
        FROM schedules s
        LEFT JOIN tasks t ON s.id = t.schedule_id AND t.is_idea = 0
    '''

    if status == 'upcoming':
        base_query += ' WHERE s.is_completed = 0'
    elif status == 'completed':
        base_query += ' WHERE s.is_completed = 1'

    base_query += ' GROUP BY s.id ORDER BY s.date ASC'

    cursor.execute(base_query)
    schedules_list = cursor.fetchall()

    conn.close()

    # 연중 일정과 일반 일정 분리
    yearly_schedules = []
    regular_schedules = []
    for schedule in schedules_list:
        if schedule['date'] == '연중':
            yearly_schedules.append(schedule)
        else:
            regular_schedules.append(schedule)

    # 월별로 그룹화 (일반 일정만)
    from collections import OrderedDict
    grouped_schedules = OrderedDict()
    for schedule in regular_schedules:
        date_str = schedule['date']
        if date_str:
            dt = parse_date(date_str)
            if dt:
                month_key = dt.strftime('%Y년 %m월')
            else:
                month_key = '날짜 미정'
        else:
            month_key = '날짜 미정'

        if month_key not in grouped_schedules:
            grouped_schedules[month_key] = []
        grouped_schedules[month_key].append(schedule)

    return render_template('schedules.html',
                           grouped_schedules=grouped_schedules,
                           yearly_schedules=yearly_schedules,
                           current_status=status)


@app.route('/schedule/<schedule_id>')
@approval_required
def schedule_detail(schedule_id):
    """일정 상세 페이지"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM schedules WHERE id = ?', (schedule_id,))
    schedule = cursor.fetchone()

    if not schedule:
        flash('일정을 찾을 수 없습니다.')
        return redirect(url_for('schedules'))

    # 실무 (is_idea=0)
    cursor.execute('''
        SELECT t.*, a.name as activist_name
        FROM tasks t
        LEFT JOIN activists a ON t.activist_id = a.id
        WHERE t.schedule_id = ? AND t.is_idea = 0
        ORDER BY t.is_completed ASC, t.priority ASC
    ''', (schedule_id,))
    action_tasks = cursor.fetchall()

    # 아이디어 (is_idea=1)
    cursor.execute('''
        SELECT t.*, a.name as activist_name
        FROM tasks t
        LEFT JOIN activists a ON t.activist_id = a.id
        WHERE t.schedule_id = ? AND t.is_idea = 1
        ORDER BY t.is_completed ASC, t.priority ASC
    ''', (schedule_id,))
    idea_tasks = cursor.fetchall()

    # 진행률 계산
    total = len(action_tasks)
    completed = sum(1 for t in action_tasks if t['is_completed'])
    progress = int((completed / total * 100)) if total > 0 else 0

    # 활동가 목록
    cursor.execute('SELECT * FROM activists')
    activists = cursor.fetchall()

    conn.close()

    return render_template('schedule_detail.html',
                           schedule=schedule,
                           action_tasks=action_tasks,
                           idea_tasks=idea_tasks,
                           activists=activists,
                           progress=progress,
                           total_tasks=total,
                           completed_tasks=completed)


def validate_date_format(date_str):
    """날짜 형식을 검증합니다. YYYY-MM-DD, YYYY-MM, YYYY-MM-시기, 또는 연중 형식 허용."""
    if not date_str:
        return True  # 빈 값은 허용 (미정)
    if date_str == '연중':
        return True  # 연중 허용
    import re
    # YYYY-MM-DD (정확한 날짜)
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            return True
        except ValueError:
            return False
    # YYYY-MM (월만)
    elif re.match(r'^\d{4}-\d{2}$', date_str):
        try:
            datetime.strptime(date_str + '-01', '%Y-%m-%d')
            return True
        except ValueError:
            return False
    # YYYY-MM-초/중순/말/미정 (대략적 시기)
    elif re.match(r'^\d{4}-\d{2}-(초|중순|말|미정)$', date_str):
        parts = date_str.split('-')
        try:
            month = int(parts[1])
            return 1 <= month <= 12
        except ValueError:
            return False
    return False


@app.route('/schedule/add', methods=['GET', 'POST'])
@approval_required
def schedule_add():
    """일정 추가"""
    if request.method == 'POST':
        date = request.form.get('date', '').strip()
        category = request.form.get('category', '').strip()
        title = request.form.get('title', '').strip()
        is_confirmed = 1 if request.form.get('is_confirmed') else 0
        details = request.form.get('details', '')

        # 유효성 검사
        errors = []
        if not title:
            errors.append('사업명을 입력해주세요.')
        if not category:
            errors.append('사업구분을 선택해주세요.')
        if date and not validate_date_format(date):
            errors.append('날짜 형식이 올바르지 않습니다. (YYYY-MM-DD, YYYY-MM, 또는 연중)')

        if errors:
            for error in errors:
                flash(error)
            return render_template('schedule_form.html', schedule=None,
                                   form_data={'date': date, 'category': category, 'title': title,
                                              'is_confirmed': is_confirmed, 'details': details})

        schedule_id = generate_schedule_id()
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO schedules (id, date, category, title, is_confirmed, details)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (schedule_id, date, category, title, is_confirmed, details))
        conn.commit()
        conn.close()

        flash('일정이 추가되었습니다.')
        return redirect(url_for('schedule_detail', schedule_id=schedule_id))

    return render_template('schedule_form.html', schedule=None, form_data=None)


@app.route('/schedule/<schedule_id>/edit', methods=['GET', 'POST'])
@approval_required
def schedule_edit(schedule_id):
    """일정 수정"""
    conn = get_db()
    cursor = conn.cursor()

    if request.method == 'POST':
        date = request.form.get('date', '').strip()
        category = request.form.get('category', '').strip()
        title = request.form.get('title', '').strip()
        is_confirmed = 1 if request.form.get('is_confirmed') else 0
        details = request.form.get('details', '')

        # 유효성 검사
        errors = []
        if not title:
            errors.append('사업명을 입력해주세요.')
        if not category:
            errors.append('사업구분을 선택해주세요.')
        if date and not validate_date_format(date):
            errors.append('날짜 형식이 올바르지 않습니다. (YYYY-MM-DD, YYYY-MM, 또는 연중)')

        if errors:
            for error in errors:
                flash(error)
            # 폼 데이터를 유지하여 다시 표시
            form_schedule = {'id': schedule_id, 'date': date, 'category': category,
                             'title': title, 'is_confirmed': is_confirmed, 'details': details}
            conn.close()
            return render_template('schedule_form.html', schedule=form_schedule, form_data=None)

        cursor.execute('''
            UPDATE schedules
            SET date = ?, category = ?, title = ?, is_confirmed = ?, details = ?
            WHERE id = ?
        ''', (date, category, title, is_confirmed, details, schedule_id))
        conn.commit()
        conn.close()

        flash('일정이 수정되었습니다.')
        return redirect(url_for('schedule_detail', schedule_id=schedule_id))

    cursor.execute('SELECT * FROM schedules WHERE id = ?', (schedule_id,))
    schedule = cursor.fetchone()
    conn.close()

    if not schedule:
        flash('일정을 찾을 수 없습니다.')
        return redirect(url_for('schedules'))

    return render_template('schedule_form.html', schedule=schedule)


@app.route('/schedule/<schedule_id>/delete', methods=['POST'])
@approval_required
def schedule_delete(schedule_id):
    """일정 삭제"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM tasks WHERE schedule_id = ?', (schedule_id,))
    cursor.execute('DELETE FROM schedules WHERE id = ?', (schedule_id,))
    conn.commit()
    conn.close()

    flash('일정이 삭제되었습니다.')
    return redirect(url_for('schedules'))


@app.route('/schedule/<schedule_id>/toggle_complete', methods=['POST'])
@approval_required
def schedule_toggle_complete(schedule_id):
    """일정 완료/미완료 토글"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT is_completed FROM schedules WHERE id = ?', (schedule_id,))
    schedule = cursor.fetchone()

    if schedule:
        new_status = 0 if schedule['is_completed'] else 1
        cursor.execute('UPDATE schedules SET is_completed = ? WHERE id = ?', (new_status, schedule_id))
        conn.commit()

    conn.close()

    referer = request.referrer or url_for('schedules')
    return redirect(referer)


# ========== 실무/TODO 관리 ==========

@app.route('/tasks')
@approval_required
def tasks():
    """전체 실무 목록"""
    conn = get_db()
    cursor = conn.cursor()

    show_completed = request.args.get('show_completed', '0') == '1'
    filter_activist = request.args.get('activist', '')
    filter_month = request.args.get('month', '')

    # 기본 쿼리
    query = '''
        SELECT t.*, s.title as schedule_title, a.name as activist_name
        FROM tasks t
        LEFT JOIN schedules s ON t.schedule_id = s.id
        LEFT JOIN activists a ON t.activist_id = a.id
        WHERE 1=1
    '''
    params = []

    if not show_completed:
        query += ' AND t.is_completed = 0'

    if filter_activist:
        query += ' AND t.activist_id = ?'
        params.append(filter_activist)

    if filter_month:
        query += " AND strftime('%Y-%m', t.deadline) = ?"
        params.append(filter_month)

    query += ' ORDER BY t.is_completed ASC, t.deadline ASC'

    cursor.execute(query, params)
    tasks_list = cursor.fetchall()

    # D-day 계산 및 월별 그룹화
    from collections import OrderedDict
    grouped_tasks = OrderedDict()
    for task in tasks_list:
        task_dict = dict(task)
        dday_text, dday_class = calc_dday(task['deadline'])
        task_dict['dday_text'] = dday_text
        task_dict['dday_class'] = dday_class

        # 월별 그룹 키
        deadline = task['deadline']
        if deadline:
            dt = parse_date(deadline)
            if dt:
                month_key = dt.strftime('%Y년 %m월')
            else:
                month_key = '마감일 미정'
        else:
            month_key = '마감일 미정'

        if month_key not in grouped_tasks:
            grouped_tasks[month_key] = []
        grouped_tasks[month_key].append(task_dict)

    cursor.execute('SELECT id, title, category, date FROM schedules ORDER BY date ASC')
    schedules_list = cursor.fetchall()

    cursor.execute('SELECT * FROM activists')
    activists = cursor.fetchall()

    # 월 목록 (필터용)
    cursor.execute("SELECT DISTINCT strftime('%Y-%m', deadline) as month FROM tasks WHERE deadline IS NOT NULL AND deadline != '' ORDER BY month DESC")
    months = [row['month'] for row in cursor.fetchall() if row['month']]

    conn.close()

    return render_template('tasks.html',
                           grouped_tasks=grouped_tasks,
                           schedules=schedules_list,
                           activists=activists,
                           months=months,
                           show_completed=show_completed,
                           filter_activist=filter_activist,
                           filter_month=filter_month)


@app.route('/task/add', methods=['POST'])
@approval_required
def task_add():
    """실무 추가"""
    schedule_id = request.form.get('schedule_id', '')
    priority = int(request.form.get('priority', 1) or 1)
    activist_id = request.form.get('activist_id', '') or None
    is_idea = 1 if request.form.get('is_idea') else 0
    is_draft = 1 if request.form.get('is_draft') else 0
    deadline = request.form.get('deadline', '')
    content = request.form.get('content', '')

    if not content.strip():
        flash('실무 내용을 입력해주세요.')
        referer = request.form.get('referer', '') or url_for('tasks')
        return redirect(referer)

    conn = get_db()
    cursor = conn.cursor()
    created_at = get_kst_now().strftime('%Y-%m-%d %H:%M')
    cursor.execute('''
        INSERT INTO tasks (schedule_id, priority, activist_id, is_idea, is_draft, deadline, content, is_completed, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
    ''', (schedule_id, priority, activist_id, is_idea, is_draft, deadline, content, created_at))
    conn.commit()
    conn.close()

    referer = request.form.get('referer', '')
    if referer:
        return redirect(referer)
    return redirect(url_for('tasks'))


@app.route('/task/<int:task_id>/toggle', methods=['POST'])
@approval_required
def task_toggle(task_id):
    """실무 완료/미완료 토글"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT is_completed FROM tasks WHERE id = ?', (task_id,))
    task = cursor.fetchone()

    new_status = 0
    if task:
        new_status = 0 if task['is_completed'] else 1
        cursor.execute('UPDATE tasks SET is_completed = ? WHERE id = ?', (new_status, task_id))
        conn.commit()

    conn.close()

    # AJAX 요청인 경우 JSON 응답
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'new_status': new_status, 'task_id': task_id})

    referer = request.referrer or url_for('tasks')
    return redirect(referer)


@app.route('/task/<int:task_id>/delete', methods=['POST'])
@approval_required
def task_delete(task_id):
    """실무 삭제"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()

    referer = request.referrer or url_for('tasks')
    return redirect(referer)


@app.route('/task/<int:task_id>/edit', methods=['POST'])
@approval_required
def task_edit(task_id):
    """실무 수정"""
    conn = get_db()
    cursor = conn.cursor()

    content = request.form.get('content', '').strip()
    activist_id = request.form.get('activist_id', '') or None
    deadline = request.form.get('deadline', '')
    is_draft = 1 if request.form.get('is_draft') else 0

    if not content:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': '내용을 입력해주세요.'})
        flash('내용을 입력해주세요.')
        return redirect(request.referrer or url_for('tasks'))

    cursor.execute('''
        UPDATE tasks SET content = ?, activist_id = ?, deadline = ?, is_draft = ?
        WHERE id = ?
    ''', (content, activist_id, deadline, is_draft, task_id))
    conn.commit()
    conn.close()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'task_id': task_id, 'content': content})

    flash('실무가 수정되었습니다.')
    referer = request.referrer or url_for('tasks')
    return redirect(referer)


# ========== 활동가 관리 ==========

@app.route('/activists')
@approval_required
def activists():
    """활동가 목록"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT a.*, COUNT(t.id) as task_count
        FROM activists a
        LEFT JOIN tasks t ON a.id = t.activist_id AND t.is_completed = 0
        GROUP BY a.id
        ORDER BY a.name ASC
    ''')
    activists_list = cursor.fetchall()

    conn.close()

    return render_template('activists.html', activists=activists_list)


@app.route('/activist/add', methods=['POST'])
@approval_required
def activist_add():
    """활동가 추가"""
    activist_id = request.form.get('id', '').strip().upper()
    name = request.form.get('name', '').strip()

    if not activist_id or not name:
        flash('ID와 이름을 모두 입력해주세요.')
        return redirect(url_for('activists'))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT id FROM activists WHERE id = ?', (activist_id,))
    if cursor.fetchone():
        flash('이미 존재하는 ID입니다.')
        conn.close()
        return redirect(url_for('activists'))

    cursor.execute('INSERT INTO activists (id, name) VALUES (?, ?)', (activist_id, name))
    conn.commit()
    conn.close()

    flash('활동가가 추가되었습니다.')
    return redirect(url_for('activists'))


@app.route('/activist/<activist_id>/edit', methods=['POST'])
@approval_required
def activist_edit(activist_id):
    """활동가 정보 수정"""
    new_id = request.form.get('new_id', '').strip().upper()
    new_name = request.form.get('new_name', '').strip()

    if not new_id or not new_name:
        flash('ID와 이름을 모두 입력해주세요.')
        return redirect(url_for('activists'))

    conn = get_db()
    cursor = conn.cursor()

    # ID 변경 시 중복 체크 (자신 제외)
    if new_id != activist_id:
        cursor.execute('SELECT id FROM activists WHERE id = ?', (new_id,))
        if cursor.fetchone():
            flash('이미 존재하는 ID입니다.')
            conn.close()
            return redirect(url_for('activists'))

        # 연관된 실무의 activist_id도 함께 업데이트
        cursor.execute('UPDATE tasks SET activist_id = ? WHERE activist_id = ?', (new_id, activist_id))
        cursor.execute('UPDATE activists SET id = ?, name = ? WHERE id = ?', (new_id, new_name, activist_id))
    else:
        cursor.execute('UPDATE activists SET name = ? WHERE id = ?', (new_name, activist_id))

    conn.commit()
    conn.close()

    flash('활동가 정보가 수정되었습니다.')
    return redirect(url_for('activists'))


@app.route('/activist/<activist_id>/delete', methods=['POST'])
@approval_required
def activist_delete(activist_id):
    """활동가 삭제"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('UPDATE tasks SET activist_id = NULL WHERE activist_id = ?', (activist_id,))
    cursor.execute('UPDATE ideas SET activist_id = NULL WHERE activist_id = ?', (activist_id,))
    cursor.execute('DELETE FROM activists WHERE id = ?', (activist_id,))
    conn.commit()
    conn.close()

    flash('활동가가 삭제되었습니다.')
    return redirect(url_for('activists'))


# ========== 사업 아이디어 ==========

@app.route('/ideas')
@approval_required
def ideas():
    """사업 아이디어 목록 - 일정과 무관한 아이디어"""
    conn = get_db()
    cursor = conn.cursor()

    show_adopted = request.args.get('show_adopted', '0') == '1'
    filter_activist = request.args.get('activist', '')

    query = '''
        SELECT i.*, a.name as activist_name
        FROM ideas i
        LEFT JOIN activists a ON i.activist_id = a.id
        WHERE 1=1
    '''
    params = []

    if not show_adopted:
        query += ' AND i.is_adopted = 0'

    if filter_activist:
        query += ' AND i.activist_id = ?'
        params.append(filter_activist)

    query += ' ORDER BY i.created_at DESC'

    cursor.execute(query, params)
    ideas_list = cursor.fetchall()

    cursor.execute('SELECT * FROM activists ORDER BY name')
    activists = cursor.fetchall()

    conn.close()

    return render_template('ideas.html',
                           ideas=ideas_list,
                           activists=activists,
                           show_adopted=show_adopted,
                           filter_activist=filter_activist)


@app.route('/idea/add', methods=['POST'])
@approval_required
def idea_add():
    """사업 아이디어 추가"""
    content = request.form.get('content', '').strip()
    activist_id = request.form.get('activist_id', '') or None

    if not content:
        flash('아이디어 내용을 입력해주세요.')
        return redirect(url_for('ideas'))

    conn = get_db()
    cursor = conn.cursor()
    created_at = get_kst_now().strftime('%Y-%m-%d %H:%M')
    cursor.execute('''
        INSERT INTO ideas (content, activist_id, is_adopted, created_at)
        VALUES (?, ?, 0, ?)
    ''', (content, activist_id, created_at))
    conn.commit()
    conn.close()

    flash('아이디어가 추가되었습니다.')
    return redirect(url_for('ideas'))


@app.route('/idea/<int:idea_id>/toggle', methods=['POST'])
@approval_required
def idea_toggle(idea_id):
    """아이디어 채택 토글"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT is_adopted FROM ideas WHERE id = ?', (idea_id,))
    idea = cursor.fetchone()

    new_status = 0
    if idea:
        new_status = 0 if idea['is_adopted'] else 1
        cursor.execute('UPDATE ideas SET is_adopted = ? WHERE id = ?', (new_status, idea_id))
        conn.commit()

    conn.close()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'new_status': new_status, 'idea_id': idea_id})

    return redirect(url_for('ideas'))


@app.route('/idea/<int:idea_id>/delete', methods=['POST'])
@approval_required
def idea_delete(idea_id):
    """아이디어 삭제"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM ideas WHERE id = ?', (idea_id,))
    conn.commit()
    conn.close()

    flash('아이디어가 삭제되었습니다.')
    return redirect(url_for('ideas'))


if __name__ == '__main__':
    debug = os.environ.get('FLASK_ENV', 'development') == 'development'
    port = int(os.environ.get('PORT', 8000))
    app.run(debug=debug, host='0.0.0.0', port=port)
