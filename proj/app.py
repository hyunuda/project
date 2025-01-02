from flask import Flask, jsonify, render_template, request, redirect, url_for, session, flash
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
import plotly.express as px
import plotly.io as pio       
from flask import g # 로그 기록을 위한 라이브러리
import requests
import re
import os
from werkzeug.utils import secure_filename
import random
from datetime import datetime, timedelta
import pytz
import module
import bcrypt
from passlib.hash import scrypt
from itsdangerous import URLSafeTimedSerializer
from flask_mail import Mail, Message
import smtplib

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # 비밀 키 설정

def log_request(user_id=None, req_type=None, content_name=None, search_text=None, status_code=None):
    """
    사용자 로그 데이터를 수집하여 API로 전송합니다.

    Args:
        user_id (str): 사용자 ID
        req_type (str): 요청 유형 (예: poster_click, movie_play, movie_search)
        content_name (str): 콘텐츠 이름 (경로 또는 제목)
        search_text (str): 사용자가 검색한 텍스트
        status_code (int): HTTP 상태 코드
    """
    # 수집 대상 req_type인지 확인
    if req_type not in ["poster_click", "movie_play", "movie_search"]:
        print(f"수집 대상이 아닌 요청 타입: {req_type}")
        return

    log_data = {
        "ip": request.remote_addr,  # 사용자 IP 주소
        "user_id": user_id or "anonymous",  # 계정 ID가 없으면 'anonymous'
        "req_type": req_type,  # 요청 유형
        "content_name": content_name or request.path,  # 콘텐츠 이름이 없으면 요청 경로
        "search_text": search_text or "",  # 검색 텍스트가 없으면 빈 문자열
        "timestamp": datetime.now().isoformat(),  # 로그 날짜/시간
        "status_code": status_code or 0,  # 상태 코드가 없으면 0
    }

    # AWS API로 로그 전송
    try:
        response = requests.post(
            "https://js8ry2hzg5.execute-api.ap-northeast-2.amazonaws.com/PROD/dev/proj3-kinesis",
            json=log_data,
        )
        response.raise_for_status()
        print("로그 데이터 전송 성공:", log_data)
    except requests.exceptions.RequestException as e:
        print(f"로그 데이터 전송 실패: {e}, 데이터: {log_data}")

@app.before_request
def before_request():
    """
    요청 전 사용자 데이터를 초기화합니다.
    """
    g.log_data = {
        "user_id": session.get("user_id"),
        "action": None,
        "content_name": None,
        "search_text": None,
        "status_code": None,
    }

@app.after_request
def after_request(response):
    """
    요청 후 사용자 로그를 기록합니다.
    """
    log_data = g.get("log_data", {})
    req_type = log_data.get("req_type")

    # 수집 대상 req_type만 로그 기록
    if req_type in ["poster_click", "movie_play", "movie_search"]:
        log_request(
            user_id=log_data.get("user_id"),
            req_type=req_type,
            content_name=log_data.get("content_name"),
            search_text=log_data.get("search_text"),
            status_code=response.status_code,
        )
    return response

# MySQL 설정
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '@mysql123',
    'database': 'movie_recommendations'
}
# csv user_info 업로드시 비밀번호 해시화 코드
# try:
#     # DB 연결
#     mydb = mysql.connector.connect(**db_config)
#     cursor = mydb.cursor(dictionary=True)

#     # 현재 비밀번호 가져오기
#     cursor.execute("SELECT user_id, user_pwd FROM user_info")
#     users = cursor.fetchall()

#     # 비밀번호 암호화 후 업데이트
#     for user in users:
#         hashed_pwd = bcrypt.hashpw(user['user_pwd'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
#         cursor.execute(
#             "UPDATE user_info SET user_pwd = %s WHERE user_id = %s",
#             (hashed_pwd, user['user_id'])
#         )
#     mydb.commit()

# except mysql.connector.Error as err:
#     print(f"Error: {err}")
# finally:
#     if cursor:
#         cursor.close()
#     if mydb:
#         mydb.close()

# Flask-Mail 설정
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'yst7804878048@gmail.com'  # 발신자 이메일 주소
app.config['MAIL_PASSWORD'] = 'lsdc uvbc gesd tiem'  # 이메일 비밀번호 또는 앱 비밀번호
app.config['MAIL_DEFAULT_SENDER'] = ('Pick&Flix Support', 'your_email@gmail.com')  # 발신자 이름 및 이메일
app.config['MAIL_DEBUG'] = True

mail = Mail(app)

#비밀번호 재설정 함수
def generate_reset_token(user_id):
    serializer = URLSafeTimedSerializer(app.secret_key)
    return serializer.dumps(user_id, salt='password-reset-salt')

def verify_reset_token(token, expiration=3600):
    serializer = URLSafeTimedSerializer(app.secret_key)
    try:
        user_id = serializer.loads(token, salt='password-reset-salt', max_age=expiration)
    except Exception:
        return None
    return user_id

#이메일 전송 함수
def send_reset_email(email, reset_link):
    try:
        msg = Message(
            "비밀번호 재설정 요청",
            recipients=[email],  # 수신자 이메일
        )
        msg.body = f"""
안녕하세요,

비밀번호를 재설정하려면 아래 링크를 클릭하세요:
{reset_link}

감사합니다,
Pick&Flix 팀
        """
        mail.send(msg)
        print("메일 전송 성공!")
    except Exception as e:
        print(f"메일 전송 실패: {e}")

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = request.form['email']
        mydb = mysql.connector.connect(**db_config)
        cursor = mydb.cursor(dictionary=True)
        try:
            # 이메일 확인
            email_parts = email.split('@')
            email_id = email_parts[0]
            domain = email_parts[1]
            cursor.execute("SELECT user_id FROM user_info WHERE email_id = %s AND domain = %s", (email_id, domain))
            user = cursor.fetchone()

            if user:
                # 토큰 생성
                token = generate_reset_token(user['user_id'])
                reset_link = url_for('reset_with_token', token=token, _external=True)

                # 이메일 전송
                send_reset_email(email, reset_link)
                flash("비밀번호 재설정 링크가 이메일로 전송되었습니다.", "info")
            else:
                flash("등록되지 않은 이메일 주소입니다.", "danger")
        finally:
            cursor.close()
            mydb.close()
    return render_template('reset_password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_with_token(token):
    user_id = verify_reset_token(token)
    if not user_id:
        flash('유효하지 않거나 만료된 토큰입니다.', 'danger')
        return redirect(url_for('login_user'))

    if request.method == 'POST':
        new_password = request.form['new_password']
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        mydb = mysql.connector.connect(**db_config)
        cursor = mydb.cursor()
        try:
            cursor.execute("UPDATE user_info SET user_pwd = %s, temp_pw_yn = 'N', retry_cnt = 0 WHERE user_id = %s", (hashed_password, user_id))
            mydb.commit()
            flash('비밀번호가 성공적으로 변경되었습니다.', 'success')
            return redirect(url_for('login_user'))
        finally:
            cursor.close()
            mydb.close()
    return render_template('reset_with_token.html')

# 메인 페이지를 login.html로 설정
@app.route('/', methods=['GET', 'POST'])
def login_user():
    if request.method == 'POST':
        email = request.form.get('email')
        user_pwd = request.form.get('user_pwd')

        if not email or not user_pwd:
            flash('이메일과 비밀번호를 모두 입력해주세요.', 'danger')
            return redirect(url_for('login_user'))

        mydb = mysql.connector.connect(**db_config)
        cursor = mydb.cursor(dictionary=True)

        try:
            # 이메일 분리
            email_parts = email.split('@')
            email_id = email_parts[0]
            domain = email_parts[1]

            # 사용자 조회
            cursor.execute("SELECT * FROM user_info WHERE email_id = %s AND domain = %s", (email_id, domain))
            user = cursor.fetchone()

            if user:
                # 계정 잠금 여부 확인
                if user['retry_cnt'] >= 5:
                    flash('계정이 잠겼습니다. 관리자에게 문의하세요.', 'danger')
                    return redirect(url_for('login_user'))

                # 비밀번호 확인 및 로그인 처리
                stored_password = user['user_pwd']

                if bcrypt.checkpw(user_pwd.encode('utf-8'), stored_password.encode('utf-8')):
                    # 로그인 성공 -> 재시도 횟수 초기화
                    cursor.execute("UPDATE user_info SET retry_cnt = 0 WHERE user_id = %s", (user['user_id'],))
                    mydb.commit()

                    # 세션 저장
                    session['user_id'] = user['user_id']
                    session['email_id'] = email
                    session['admin_yn'] = user['admin_yn']

                    flash('로그인 성공!', 'success')

                    # 관리자 또는 신규 사용자에 따른 리다이렉션
                    if user['admin_yn'] == 'Y':
                        flash('관리자로 로그인하셨습니다.', 'success')
                        return redirect(url_for('admin_dashboard'))
                    elif user['new_user_yn'] == 'Y':
                        return redirect(url_for('select_genres'))
                    else:
                        return redirect(url_for('recommendations'))
                else:
                    # 로그인 실패 -> 재시도 횟수 증가
                    retry_attempts = user['retry_cnt'] + 1
                    cursor.execute("UPDATE user_info SET retry_cnt = %s WHERE user_id = %s", (retry_attempts, user['user_id']))
                    mydb.commit()

                    # 5회 실패 시 계정 잠금 처리
                    if retry_attempts >= 5:
                        cursor.execute("UPDATE user_info SET temp_pw_yn = 'Y' WHERE user_id = %s", (user['user_id'],))
                        mydb.commit()
                        flash('5번 이상 실패했습니다. 계정이 잠겼습니다. 관리자에게 문의하세요.', 'danger')
                    else:
                        remaining_attempts = 5 - retry_attempts
                        flash(f'로그인 실패! 남은 시도 횟수: {remaining_attempts}', 'danger')

        except IndexError:
            flash('유효한 이메일 형식이 아닙니다.', 'danger')
        finally:
            cursor.close()
            mydb.close()
    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        user_name = request.form.get('user_name')  # 사용자 이름 추가
        email = request.form.get('email')
        user_pwd = request.form['user_pwd']  # 비밀번호 가져오기
        date_of_birth_str = request.form['date_of_birth']  # 생년월일 추가
        gender = request.form.get('gender')
        province = request.form.get('province')  # 프로빈스 이름으로 변경
   
        # 비밀번호 해싱: bcrypt 사용
        hashed_password = bcrypt.hashpw(user_pwd.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        # 성별 값 변환
        gender_mapping = {'남성': 'M', '여성': 'F', '기타': 'N'}
        gender = gender_mapping.get(gender, 'N')  # 잘못된 값은 'N'으로 기본 설정

        # 이메일 형식 유효성 검사
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            flash('유효한 이메일 주소를 입력하세요.', 'danger')
            return redirect(url_for('signup'))

        # 생년월일을 날짜 형식으로 변환
        try:
            date_of_birth = datetime.strptime(date_of_birth_str, '%Y-%m-%d').strftime('%Y%m%d')
        except ValueError:
            flash('생년월일 형식이 올바르지 않습니다. 올바른 형식: YYYY-MM-DD', 'danger')
            return redirect(url_for('signup'))

        # 이메일 분리
        email_parts = email.split('@')
        email_id = email_parts[0]
        domain = email_parts[1]

        # DB에 저장
        mydb = mysql.connector.connect(**db_config)
        cursor = mydb.cursor(dictionary=True)
        try:
            # 이메일 중복 확인
            cursor.execute("SELECT * FROM user_info WHERE email_id = %s AND domain = %s", (email_id, domain))
            existing_user = cursor.fetchone()
            if existing_user:
                flash('이미 사용 중인 이메일입니다. 다른 이메일을 사용하세요.', 'danger')
                return redirect(url_for('signup'))

            # 회원가입 정보 저장
            cursor.execute(
                "INSERT INTO user_info (user_name, email_id, domain, user_pwd, province, gender, date_of_birth, new_user_yn, admin_yn, retry_cnt, temp_pw_yn) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (user_name, email_id, domain, hashed_password, province, gender, date_of_birth, 'Y', 'N', '0', 'N')
            )
            mydb.commit()
            flash('회원가입이 완료되었습니다!', 'success')
            return redirect(url_for('login_user'))
        except mysql.connector.Error as err:
            flash(f'회원가입 중 오류가 발생했습니다: {err}', 'danger')
        finally:
            cursor.close()
            mydb.close()
    return render_template('signup.html')

@app.route('/admin-signup', methods=['GET', 'POST'])
def admin_signup():
    if request.method == 'POST':
        # 폼 데이터 수집
        user_name = request.form.get('user_name')
        email = request.form.get('email')
        user_pwd = request.form['user_pwd']  # 비밀번호 가져오기
        province = request.form.get('province')
        gender = request.form.get('gender')
        date_of_birth_str = request.form['date_of_birth']

        # 비밀번호 해싱: bcrypt 사용
        hashed_password = bcrypt.hashpw(user_pwd.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        # 성별 값 변환
        gender_mapping = {'남성': 'M', '여성': 'F', '기타': 'N'}
        gender = gender_mapping.get(gender, 'N')

        # 디버그: 전달된 폼 데이터 확인
        print("Received Form Data:", request.form)

        # 이메일 형식 유효성 검사
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            flash('유효한 이메일 주소를 입력하세요.', 'danger')
            return redirect(url_for('admin_signup'))

        # 생년월일 처리
        try:
            date_of_birth = datetime.strptime(date_of_birth_str, '%Y-%m-%d').strftime('%Y%m%d')
        except ValueError:
            flash('생년월일 형식이 올바르지 않습니다.', 'danger')
            return redirect(url_for('admin_signup'))

        # 이메일 분리
        email_parts = email.split('@')
        email_id, domain = email_parts[0], email_parts[1]

        # 디버그: 변환된 데이터 확인
        print(f"Parsed Data: user_name={user_name}, email_id={email_id}, domain={domain}, gender={gender}")

        # DB 저장
        mydb = mysql.connector.connect(**db_config)
        cursor = mydb.cursor(dictionary=True)
        try:
            # 이메일 중복 확인
            cursor.execute("SELECT * FROM user_info WHERE email_id = %s AND domain = %s", (email_id, domain))
            if cursor.fetchone():
                flash('이미 사용 중인 이메일입니다.', 'danger')
                return redirect(url_for('admin_signup'))

            # 관리자 정보 삽입
            cursor.execute(
                """
                INSERT INTO user_info (
                    user_name, email_id, domain, user_pwd, province, gender,
                    date_of_birth, new_user_yn, admin_yn, retry_cnt, temp_pw_yn
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_name, email_id, domain, hashed_password, province, gender, 
                    date_of_birth, 'N', 'Y', 0, 'N'  # admin_yn='Y'
                )
            )

            # 디버그: SQL 실행 결과 확인
            print(f"Rows inserted: {cursor.rowcount}")

            # 변경 사항 커밋
            mydb.commit()

            flash('관리자 회원가입이 완료되었습니다!', 'success')
            return redirect(url_for('login_user'))

        except mysql.connector.Error as err:
            # 디버그: SQL 오류 확인
            print(f"SQL Error: {err}")
            flash(f"회원가입 중 오류가 발생했습니다: {err}", 'danger')

        finally:
            # 리소스 정리
            cursor.close()
            mydb.close()

    return render_template('admin_signup.html')

# 영화 추천 메인페이지

from module import recommend_newbie_movies, recommend_oldbie_movies  # module.py에서 함수 가져오기

@app.route('/recommendations')
def recommendations():
    if 'user_id' not in session:
        return redirect(url_for('login_user'))

    user_id = session['user_id']

    try:
        mydb = mysql.connector.connect(**db_config)
        cursor = mydb.cursor(dictionary=True)

        # 사용자 이름 가져오기
        cursor.execute("SELECT user_name FROM user_info WHERE user_id = %s", (user_id,))
        user_info = cursor.fetchone()
        user_name = user_info['user_name'] if user_info else "회원님"  # 이름이 없으면 "회원님" 기본값 사용

        # 사용자 시청 완료율이 80% 이상인 영화 개수 확인
        cursor.execute("""
            SELECT COUNT(*) AS watched_count
            FROM user_watched_log
            WHERE user_id = %s AND watch_per >= 80
        """, (user_id,))
        watched_count_result = cursor.fetchone()
        watched_count = watched_count_result['watched_count'] if watched_count_result else 0

        # AI 추천 영화 로직
        personal_recommendations = []  # 초기화

        if watched_count <= 5:
            # 시청 완료율 80% 이상의 영화가 5개 이하인 경우 - Newbie 추천
            newbie_recommendations_df = recommend_newbie_movies(user_id)
            if newbie_recommendations_df is not None and not newbie_recommendations_df.empty:
                personal_recommendations = [
                    {'movie_id': row['movieID'], 'movie_title': row['title']}
                    for _, row in newbie_recommendations_df.iterrows()
                ]
        else:
            # 시청 완료율 80% 이상의 영화가 5개 이상인 경우 - Oldbie 추천
            oldbie_recommendations_df = recommend_oldbie_movies(user_id)
            if oldbie_recommendations_df is not None and not oldbie_recommendations_df.empty:
                personal_recommendations = [
                    {'movie_id': row['movie_id'], 'movie_title': row['movie_title']}
                    for _, row in oldbie_recommendations_df.iterrows()
                ]

        # personal_recommendations를 반환하거나 사용


        # 전체 영화 TOP 10 (조회수 많은 순)
        cursor.execute("""
        SELECT mi.movie_id, mi.movie_title, COUNT(uwl.user_id) AS view_count
            FROM user_watched_log uwl
            JOIN movie_info mi ON uwl.movie_id = mi.movie_id
            GROUP BY mi.movie_id, mi.movie_title
            ORDER BY view_count DESC
            LIMIT 10
        """)
        top_movies = cursor.fetchall()

        #시청 중인 영화 (시청률 100% 미만인 경우만 포함)
        cursor.execute("""
            SELECT uwl.movie_id, mi.movie_title, MAX(uwl.watch_per) AS max_watch_per
            FROM user_watched_log uwl
            JOIN movie_info mi ON uwl.movie_id = mi.movie_id
            WHERE uwl.user_id = %s
            AND uwl.movie_id NOT IN (
                SELECT movie_id
                FROM user_watched_log
                WHERE user_id = %s AND watch_per = 100
            )
            GROUP BY uwl.movie_id, mi.movie_title
            ORDER BY MAX(uwl.watch_stop_time) DESC, MAX(uwl.watch_per) DESC;
        """, (user_id, user_id))

        currently_watching = cursor.fetchall()

        # 회원님들이 많이 보는 영화 (나이대와 성별에 따른 시청 횟수 기준 상위 10개)
        age_group_case = """
            CASE
                WHEN TIMESTAMPDIFF(YEAR, STR_TO_DATE(ui.date_of_birth, '%Y%m%d'), CURDATE()) BETWEEN 10 AND 19 THEN '10대'
                WHEN TIMESTAMPDIFF(YEAR, STR_TO_DATE(ui.date_of_birth, '%Y%m%d'), CURDATE()) BETWEEN 20 AND 29 THEN '20대'
                WHEN TIMESTAMPDIFF(YEAR, STR_TO_DATE(ui.date_of_birth, '%Y%m%d'), CURDATE()) BETWEEN 30 AND 39 THEN '30대'
                WHEN TIMESTAMPDIFF(YEAR, STR_TO_DATE(ui.date_of_birth, '%Y%m%d'), CURDATE()) BETWEEN 40 AND 49 THEN '40대'
                WHEN TIMESTAMPDIFF(YEAR, STR_TO_DATE(ui.date_of_birth, '%Y%m%d'), CURDATE()) BETWEEN 50 AND 59 THEN '50대'
                WHEN TIMESTAMPDIFF(YEAR, STR_TO_DATE(ui.date_of_birth, '%Y%m%d'), CURDATE()) >= 60 THEN '60대 이상'
                ELSE '기타'
            END
        """

        # 사용자 정보에서 나이대와 성별 가져오기
        cursor.execute("SELECT date_of_birth, gender FROM user_info WHERE user_id = %s", (user_id,))
        user_data = cursor.fetchone()

        # 나이대 계산
        if user_data and user_data['date_of_birth']:
            user_dob_str = user_data['date_of_birth']  # '20001212' 형식
            user_dob = datetime.strptime(user_dob_str, '%Y%m%d').date()  # 문자열을 날짜 형식으로 변환
            current_date = datetime.now().date()
            user_age = current_date.year - user_dob.year - ((current_date.month, current_date.day) < (user_dob.month, user_dob.day))
            user_age_group = (
                '10대' if 10 <= user_age <= 19 else
                '20대' if 20 <= user_age <= 29 else
                '30대' if 30 <= user_age <= 39 else
                '40대' if 40 <= user_age <= 49 else
                '50대' if 50 <= user_age <= 59 else
                '60대 이상' if user_age >= 60 else
                '기타'
            )
        else:
            user_age_group = '기타'  # 기본값

        # 성별
        if user_data and user_data['gender']:
            user_gender = user_data['gender']  # 'M', 'F', 'N'
        else:
            user_gender = 'N'  # 기본값: 기타

        # 나이대와 성별로 필터링된 인기 영화 조회
        cursor.execute(f"""
            SELECT mi.movie_id, mi.movie_title, COUNT(uwl.user_id) AS watch_count
            FROM user_watched_log uwl
            JOIN user_info ui ON uwl.user_id = ui.user_id
            JOIN movie_info mi ON uwl.movie_id = mi.movie_id
            WHERE {age_group_case} = %s
            AND ui.gender = %s
            GROUP BY mi.movie_id, mi.movie_title
            ORDER BY watch_count DESC
            LIMIT 10
        """, (user_age_group, user_gender))
        popular_movies = cursor.fetchall()

        # 곧 서비스가 종료될 영화 (end_time 기준 오름차순, 7일 이내 종료 영화)
        cursor.execute("""
            SELECT movie_id, movie_title 
            FROM movie_info
            WHERE end_time BETWEEN DATE_FORMAT(NOW(), '%Y%m%d') AND DATE_FORMAT(DATE_ADD(NOW(), INTERVAL 7 DAY), '%Y%m%d')
            ORDER BY end_time ASC
        """)
        expiring_movies = cursor.fetchall()

        # 전체 영화 (movie_id 기준 오름차순, 상위 30개)
        cursor.execute("SELECT movie_id, movie_title FROM movie_info ORDER BY movie_id ASC LIMIT 30")
        all_movies = cursor.fetchall()

    except mysql.connector.Error as err:
        flash(f"데이터베이스 오류: {err}", 'danger')
        return redirect(url_for('login_user'))
    finally:
        cursor.close()
        mydb.close()

    return render_template(
        'recommendations.html',
        user_name=user_name,  # 사용자 이름 전달
        personal_recommendations=personal_recommendations,
        top_movies=top_movies,
        currently_watching=currently_watching,
        popular_movies=popular_movies,
        expiring_movies=expiring_movies,
        all_movies=all_movies
    )
@app.route('/get-notifications', methods=['GET'])
def get_notifications():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session['user_id']
    try:
        mydb = mysql.connector.connect(**db_config)
        cursor = mydb.cursor(dictionary=True)

        # 읽지 않은 알람 가져오기
        cursor.execute("""
            SELECT 
                a.d_date, 
                a.movie_id, 
                m.movie_title  -- movie_title 추가
            FROM announce a
            JOIN movie_info m ON a.movie_id = m.movie_id
            WHERE a.user_id = %s AND a.read_yn = 'N'
        """, (user_id,))
        notifications = cursor.fetchall()

    except mysql.connector.Error as err:
        print(f"Database error: {err}")
        return jsonify({'error': 'Database connection failed'}), 500

    finally:
        if cursor:
            cursor.close()
        if mydb:
            mydb.close()

    return jsonify(notifications)

@app.route('/mark-notifications-read-v2/<string:movie_id>', methods=['POST'])
def mark_notification_read_v2(movie_id):
    """
    특정 알림을 읽음 처리합니다.
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized', 'message': 'User not logged in'}), 401

    user_id = session['user_id']
    mydb = mysql.connector.connect(**db_config)
    cursor = mydb.cursor()

    try:
        # 특정 알림 읽음 처리
        cursor.execute("""
            UPDATE announce
            SET read_yn = 'Y'
            WHERE user_id = %s AND movie_id = %s AND read_yn = 'N'
        """, (user_id, movie_id))
        mydb.commit()

        # 변경된 행 수 확인
        if cursor.rowcount == 0:
            return jsonify({'error': 'No notifications updated', 'message': 'Notification not found'}), 404

        return jsonify({'success': True, 'message': 'Notification marked as read'}), 200
    except mysql.connector.Error as e:
        print(f"Database error: {e}")
        return jsonify({'error': 'Database error', 'message': str(e)}), 500
    finally:
        cursor.close()
        mydb.close()



@app.route('/load-more-movies')
def load_more_movies():
    offset = int(request.args.get('offset', 0))
    limit = int(request.args.get('limit', 30))

    try:
        mydb = mysql.connector.connect(**db_config)
        cursor = mydb.cursor(dictionary=True)

        # movie_id 기준 오름차순으로 영화 데이터를 가져오기
        cursor.execute("""
            SELECT movie_id, movie_title
            FROM movie_info
            ORDER BY movie_id ASC
            LIMIT %s OFFSET %s
        """, (limit, offset))
        more_movies = cursor.fetchall()

    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        mydb.close()

    return jsonify(more_movies)

@app.route('/get-genres', methods=['GET'])
def get_genres():
    try:
        # MySQL 연결
        mydb = mysql.connector.connect(**db_config)
        cursor = mydb.cursor(dictionary=True)

        # SQL 실행
        cursor.execute("SELECT genre_id, genre_title FROM genre")
        genres = cursor.fetchall()

        # JSON 변환
        result = [{'genre_id': row['genre_id'], 'genre_title': row['genre_title']} for row in genres]
        return jsonify(result)
    except mysql.connector.Error as err:
        # 에러 처리
        return jsonify({'error': str(err)}), 500
    finally:
        # 리소스 정리
        cursor.close()
        mydb.close()
        
@app.route('/genre-search', methods=['POST'])
def genre_search():
    mydb = None
    cursor = None
    try:
        data = request.get_json()
        genres = data.get('genres', [])

        if not genres:
            return jsonify([])

        genre_count = len(genres)
        placeholders = ', '.join(['%s'] * genre_count)
        query = f"""
            SELECT mi.movie_id, mi.movie_title, mi.poster_path AS poster
            FROM movie_info mi
            JOIN movie_genre mg ON mi.movie_id = mg.movie_id
            WHERE mg.genre_id IN ({placeholders})
            GROUP BY mi.movie_id
            HAVING COUNT(DISTINCT mg.genre_id) = {genre_count}
        """

        mydb = mysql.connector.connect(**db_config)
        cursor = mydb.cursor(dictionary=True)
        cursor.execute(query, tuple(genres))
        movies = cursor.fetchall()

        # Flask의 static 디렉토리를 기준으로 경로 수정
        for movie in movies:
            movie['poster'] = f"static/{movie['poster']}"

        return jsonify([{
            'movie_id': m['movie_id'],
            'title': m['movie_title'],
            'poster': m['poster']
        } for m in movies])

    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500

    finally:
        if cursor:
            cursor.close()
        if mydb:
            mydb.close()

@app.route('/genre-search', methods=['GET'])
def render_genre_search():
    return render_template('genre_search.html')

@app.route('/movie_details/<string:movie_id>')
def movie_details(movie_id):
    user_id = session.get('user_id')
    mydb = mysql.connector.connect(**db_config)
    cursor = mydb.cursor(dictionary=True, buffered=True)  # buffered 추가

    try:
        # 영화 정보 가져오기
        query = """
        SELECT 
            movie_info.movie_id,
            movie_info.movie_title AS title,
            movie_info.release_year,
            movie_info.watch_grade,
            COALESCE(movie_info.poster_path, 'img/default_poster.jpg') AS poster,
            GROUP_CONCAT(DISTINCT genre.genre_title SEPARATOR ', ') AS genres,
            GROUP_CONCAT(DISTINCT movie_director.director SEPARATOR ', ') AS directors,
            GROUP_CONCAT(DISTINCT movie_actor.actor SEPARATOR ', ') AS actors,
            GROUP_CONCAT(DISTINCT movie_country.country SEPARATOR ', ') AS country,
            GROUP_CONCAT(DISTINCT movie_meta.keyword SEPARATOR ', ') AS keywords,
            MAX(movie_synopsis.synopsis1) AS synopsis1,
            mg.grade_avg
        FROM 
            movie_info
        LEFT JOIN movie_genre ON movie_info.movie_id = movie_genre.movie_id
        LEFT JOIN genre ON movie_genre.genre_id = genre.genre_id
        LEFT JOIN movie_director ON movie_info.movie_id = movie_director.movie_id
        LEFT JOIN movie_actor ON movie_info.movie_id = movie_actor.movie_id
        LEFT JOIN movie_country ON movie_info.movie_id = movie_country.movie_id
        LEFT JOIN movie_meta ON movie_info.movie_id = movie_meta.movie_id
        LEFT JOIN movie_synopsis ON movie_info.movie_id = movie_synopsis.movie_id
        LEFT JOIN movie_grade mg ON movie_info.movie_id = mg.movie_id
        WHERE 
            movie_info.movie_id = %s
        GROUP BY 
            movie_info.movie_id, mg.grade_avg;
        """
        cursor.execute(query, (movie_id,))
        movie = cursor.fetchone()

        if not movie:
            print(f"Movie with ID {movie_id} not found")
            return render_template('404.html', message="영화를 찾을 수 없습니다."), 404

        # 사용자 평점 가져오기
        if user_id:
            cursor.execute("""
                SELECT grade FROM user_watched_log 
                WHERE user_id = %s AND movie_id = %s
            """, (user_id, movie_id))
            user_grade = cursor.fetchone()
            movie['user_grade'] = user_grade['grade'] if user_grade and 'grade' in user_grade else None
        else:
            movie['user_grade'] = None

        # 찜 상태 확인
        if user_id:
            cursor.execute("""
                SELECT 1 FROM wishlist WHERE user_id = %s AND movie_id = %s
            """, (user_id, movie_id))
            in_wishlist = cursor.fetchone() is not None
        else:
            in_wishlist = False

        movie['in_wishlist'] = in_wishlist
        g.log_data = {
            "user_id": user_id,
            "req_type": "poster_click",
            "content_name": movie["title"],
        }

        return render_template('movie_details.html', movie=movie)

    except mysql.connector.Error as err:
        print(f"Database error: {err}")
        return render_template('error.html', message="데이터베이스 오류가 발생했습니다. 나중에 다시 시도해주세요."), 500

    except Exception as e:
        print(f"Unexpected error: {e}")
        return render_template('error.html', message="예기치 않은 오류가 발생했습니다. 나중에 다시 시도해주세요."), 500

    finally:
        cursor.close()
        mydb.close()



# 영화 재생
@app.route('/play_movie/<string:movie_id>')
def play_movie(movie_id):
    mydb = mysql.connector.connect(**db_config)
    cursor = mydb.cursor(dictionary=True)

    try:
        # 영화 정보 및 영상 경로 가져오기
        cursor.execute("""
            SELECT movie_id, movie_title, video_path
            FROM movie_info
            WHERE movie_id = %s
        """, (movie_id,))
        movie = cursor.fetchone()

        if not movie or not movie['video_path']:
            flash("영화 영상이 존재하지 않습니다.", "danger")
            return redirect(url_for('recommendations'))

        # 영화 재생 로그 기록
        g.log_data = {
            "user_id": session.get('user_id'),
            "req_type": "movie_play",
            "content_name": movie["movie_title"],
        }

        return render_template('play_movie.html', movie=movie)
    except mysql.connector.Error as err:
        flash(f"데이터베이스 오류: {err}", "danger")
        return redirect(url_for('recommendations'))
    finally:
        cursor.close()
        mydb.close()

@app.route('/save-watch-log', methods=['POST'])
def save_watch_log():
    data = request.get_json()
    movie_id = data.get('movie_id')
    watch_percentage = int(data.get('watch_percentage', 0))  # 기본값 0
    rating = int(data.get('rating', 0))  # 평점은 기본값 0
    user_id = session.get('user_id')  # 현재 로그인된 사용자 ID 가져오기
    date = data.get('date')  # 클라이언트에서 전달받은 날짜
    watch_start_time = data.get('start_time')  # 시작 시간
    watch_stop_time = data.get('stop_time')  # 종료 시간
    today_date = datetime.now().strftime('%Y%m%d')  # 오늘 날짜

    # 날짜 처리: 클라이언트에서 날짜를 전달받지 않으면 오늘 날짜 사용
    d_date = date if date else today_date

    # 필수 데이터 확인
    if not all([movie_id, watch_start_time, watch_stop_time]):
        return jsonify({"error": "필수 데이터가 누락되었습니다."}), 400

    try:
        mydb = mysql.connector.connect(**db_config)
        cursor = mydb.cursor()

        # 한국 시간대 설정
        kst = pytz.timezone('Asia/Seoul')

        # 시작 시간과 종료 시간을 한국 시간으로 변환
        start_dt = datetime.strptime(watch_start_time, '%Y%m%d%H%M%S').replace(tzinfo=pytz.utc).astimezone(kst)
        stop_dt = datetime.strptime(watch_stop_time, '%Y%m%d%H%M%S').replace(tzinfo=pytz.utc).astimezone(kst)

        # 시청 시간 계산 (초 단위)
        watch_time = (stop_dt - start_dt).total_seconds()

        # 시청 시간이 음수일 경우 처리
        if watch_time < 0:
            return jsonify({"error": "종료 시간이 시작 시간보다 빠릅니다."}), 400

        # day_seq_no 계산
        cursor.execute(
            """
            SELECT COALESCE(MAX(day_seq_no), 0) + 1
            FROM user_watched_log
            WHERE user_id = %s AND d_date = %s
            """,
            (user_id, d_date)
        )
        day_seq_no = cursor.fetchone()[0]

        # 데이터 삽입 또는 업데이트
        query = """
            INSERT INTO user_watched_log (
                user_id, movie_id, watch_per, grade, d_date, day_seq_no,
                watch_start_time, watch_stop_time, watch_time
            )
            SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s
            FROM DUAL
            WHERE %s > 0 OR %s > 0  -- watch_per와 grade 중 하나라도 0보다 큰 경우에만 삽입
            ON DUPLICATE KEY UPDATE
                watch_per = GREATEST(VALUES(watch_per), watch_per),
                grade = GREATEST(VALUES(grade), grade),
                watch_stop_time = IF(VALUES(watch_stop_time) > watch_stop_time, VALUES(watch_stop_time), watch_stop_time),
                watch_time = VALUES(watch_time)
        """
        cursor.execute(
            query,
            (
                user_id, movie_id, watch_percentage, rating, d_date, day_seq_no,
                start_dt.strftime('%Y%m%d%H%M%S'), stop_dt.strftime('%Y%m%d%H%M%S'), watch_time,
                watch_percentage, rating
            )
        )

        mydb.commit()

        return jsonify({"message": "Success"}), 200
    except mysql.connector.Error as err:
        print(f"SQL Error: {err}")  # 콘솔에 상세 에러 출력
        return jsonify({"message": f"Database error: {err}"}), 500
    except Exception as e:
        print(f"Unexpected Error: {e}")  # 다른 예외 상황 처리
        return jsonify({"message": f"Unexpected error: {e}"}), 500
    finally:
        # 리소스 정리
        if cursor:
            cursor.close()
        if mydb:
            mydb.close()

@app.route('/logout')
def logout():
    session.clear()
    flash('로그아웃 되었습니다.', 'info')
    return redirect(url_for('login_user'))

@app.route('/test_db')
def test_db():
    try:
        mydb = mysql.connector.connect(**db_config)
        if mydb.is_connected():
            return "MySQL 데이터베이스에 성공적으로 연결되었습니다!"
    except mysql.connector.Error as err:
        return f"데이터베이스 연결 실패: {err}"
    finally:
        if mydb.is_connected():
            mydb.close()

# @app.route('/root_graph', methods=['GET', 'POST'])
# def index():
#     graph_html = None
#     user_stats = None
#     fig = None

#     if request.method == 'POST':
#         user_id = request.form.get('user_id')
#         x_var = request.form.get('x_variable')
#         y_var = request.form.get('y_variable')
#         chart_type = request.form.get('chart_type')

#         filtered_df = df[df['이메일'] == user_id]

#         if not filtered_df.empty and x_var and y_var:
#             if chart_type == 'line':
#                 fig = px.line(filtered_df, x=x_var, y=y_var, title=f'Line Chart: {y_var} vs {x_var} for {user_id}')
#             elif chart_type == 'bar':
#                 fig = px.bar(filtered_df, x=x_var, y=y_var, title=f'Bar Chart: {y_var} vs {x_var} for {user_id}')
#             elif chart_type == 'scatter':
#                 fig = px.scatter(filtered_df, x=x_var, y=y_var, title=f'Scatter Plot: {y_var} vs {x_var} for {user_id}')

#         if fig:
#             graph_html = pio.to_html(fig, full_html=False)

#             user_stats = {
#                 '시청시간 평균': filtered_df['시청시간'].mean(),
#                 '시청시간 합계': filtered_df['시청시간'].sum(),
#                 '시정갯수 평균': filtered_df['시정갯수'].mean(),
#                 '시정갯수 합계': filtered_df['시정갯수'].sum(),
#                 '지불금액 평균': filtered_df['지불금액'].mean(),
#                 '지불금액 합계': filtered_df['지불금액'].sum(),
#             }

#     user_ids = df['이메일'].unique()
#     return render_template('root_graph.html', graph_html=graph_html, df=df, user_ids=user_ids, user_stats=user_stats)


@app.route('/select-genres', methods=['GET', 'POST'])
def select_genres():
    if 'user_id' not in session:
        return redirect(url_for('login_user'))

    if request.method == 'POST':
        # 선택된 장르 목록 가져오기
        selected_genres = request.form['genres'].split(',')  # 문자열을 리스트로 변환

        # 최소 1개 이상, 최대 5개 이하의 장르 선택 검증
        if len(selected_genres) < 1:
            flash('최소 한 개의 장르를 선택하세요.', 'danger')
            return redirect(url_for('select_genres'))
        
        if len(selected_genres) > 5:
            flash('최대 5개의 장르만 선택할 수 있습니다.', 'danger')
            return redirect(url_for('select_genres'))

        user_id = session['user_id']
        mydb = mysql.connector.connect(**db_config)
        cursor = mydb.cursor()

        try:
            # 유효한 genre_id 확인
            cursor.execute("SELECT genre_id FROM genre")
            valid_genres = [row[0] for row in cursor.fetchall()]

            # 기존 사용자의 장르 데이터 삭제
            cursor.execute("DELETE FROM user_pref_genres WHERE user_id = %s", (user_id,))

            for genre_id in selected_genres:
                if genre_id not in valid_genres:
                    flash(f"유효하지 않은 장르 ID: {genre_id}", 'danger')
                    return redirect(url_for('select_genres'))

            # 새로 선택된 장르 저장
            for genre_id in selected_genres:
                cursor.execute(
                    "INSERT INTO user_pref_genres (user_id, genre_id) VALUES (%s, %s)",
                    (user_id, genre_id)
                )

            # `new_user_yn` 업데이트
            cursor.execute("UPDATE user_info SET new_user_yn = 'N' WHERE user_id = %s", (user_id,))
            mydb.commit()

            flash('선호 장르가 저장되었습니다!', 'success')
            return redirect(url_for('recommendations'))  # 추천 화면으로 이동
        except mysql.connector.Error as err:
            flash(f'장르 저장 중 오류가 발생했습니다: {err}', 'danger')
        finally:
            cursor.close()
            mydb.close()

    return render_template('select_genres.html')

# 찜리스트 페이지 라우트
@app.route('/wishlist', methods=['GET'])
def wishlist():
    if 'user_id' not in session:
        flash('로그인이 필요합니다.', 'danger')
        return redirect(url_for('login_user'))
    
    user_id = session['user_id']

    try:
        # 찜리스트 데이터를 가져오기
        mydb = mysql.connector.connect(**db_config)
        cursor = mydb.cursor(dictionary=True)
        query = """
            SELECT mi.movie_id, mi.movie_title, mi.poster_path, mi.release_year
            FROM wishlist wl
            JOIN movie_info mi ON wl.movie_id = mi.movie_id
            WHERE wl.user_id = %s
        """
        cursor.execute(query, (user_id,))
        wishlist_movies = cursor.fetchall()

        return render_template('wishlist.html', movies=wishlist_movies)
    except mysql.connector.Error as err:
        flash(f'데이터베이스 오류: {err}', 'danger')
        return redirect(url_for('recommendations'))
    finally:
        cursor.close()
        mydb.close()

@app.route('/add_to_wishlist/<string:movie_id>', methods=['POST'])
def add_to_wishlist(movie_id):
    # 사용자가 로그인하지 않은 경우
    if 'user_id' not in session:
        return jsonify({'error': '로그인이 필요합니다.'}), 401

    user_id = session['user_id']  # 현재 로그인된 사용자 ID
    try:
        mydb = mysql.connector.connect(**db_config)
        cursor = mydb.cursor()

        # 같은 날짜에 추가된 항목 중 가장 큰 day_seq_no를 계산하여 +1
        cursor.execute("""
            SELECT COALESCE(MAX(day_seq_no), 0) + 1
            FROM wishlist
            WHERE user_id = %s AND d_date = CURDATE()
        """, (user_id,))
        day_seq_no = cursor.fetchone()[0]

        # 위시리스트에 삽입 (중복 방지)
        query = """
            INSERT INTO wishlist (user_id, movie_id, d_date, day_seq_no)
            VALUES (%s, %s, REPLACE(CURDATE(), '-', ''), %s)
            ON DUPLICATE KEY UPDATE movie_id = movie_id
        """
        cursor.execute(query, (user_id, movie_id, day_seq_no))
        mydb.commit()

        return jsonify({'message': '위시리스트에 추가되었습니다!'}), 200
    except mysql.connector.Error as err:
        return jsonify({'error': f'데이터베이스 오류: {err}'}), 500
    finally:
        cursor.close()
        mydb.close()

# 위시리스트 삭제

@app.route('/remove-from-wishlist/<string:movie_id>', methods=['POST'])
def remove_from_wishlist(movie_id):
    if 'user_id' not in session:
        return jsonify({'message': '로그인이 필요합니다.'}), 401

    user_id = session['user_id']

    try:
        mydb = mysql.connector.connect(**db_config)
        cursor = mydb.cursor()

        # 데이터 삭제 쿼리
        query = """
            DELETE FROM wishlist 
            WHERE user_id = %s AND movie_id = %s
        """
        cursor.execute(query, (user_id, movie_id))
        mydb.commit()

        return jsonify({'message': '찜목록에서 삭제되었습니다!'}), 200
    except mysql.connector.Error as err:
        return jsonify({'message': f'데이터베이스 오류: {err}'}), 500
    finally:
        cursor.close()
        mydb.close()

@app.route('/search-content', methods=['GET'])
def search_content():
    query = request.args.get('query')

    if not query:
        flash('검색어를 입력하세요.', 'warning')
        return redirect(url_for('recommendations'))

    try:
        mydb = mysql.connector.connect(**db_config)
        cursor = mydb.cursor(dictionary=True)

        # 검색 쿼리를 준비
        search_query = f"%{query}%"

        # 영화 제목, 배우 이름, 감독 이름으로 검색
        cursor.execute("""
            SELECT * FROM movie_info 
            WHERE movie_id IN (
                SELECT movie_id FROM movie_info WHERE movie_title LIKE %s
                UNION
                SELECT movie_id FROM movie_director WHERE director LIKE %s
                UNION
                SELECT movie_id FROM movie_actor WHERE actor LIKE %s
            )
        """, (search_query, search_query, search_query))
        movies = cursor.fetchall()

        # 검색 로그 기록
        g.log_data = {
            "user_id": session.get("user_id"),
            "req_type": "movie_search",
            "search_text": query,
        }

    except mysql.connector.Error as err:
        flash(f'검색 중 오류가 발생했습니다: {err}', 'danger')
        movies = []
    finally:
        cursor.close()
        mydb.close()

    if not movies:
        flash('검색된 콘텐츠가 없습니다.', 'info')

    return render_template('search_results.html', search_results=movies, query=query)

    
@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login_user'))
    
    user_id = session['user_id']

    try:
        # 데이터베이스 연결 및 사용자 정보 조회
        mydb = mysql.connector.connect(**db_config)
        cursor = mydb.cursor(dictionary=True)
        query = """
        SELECT email_id, domain, user_name, province, gender, date_of_birth
        FROM user_info
        WHERE user_id = %s
        """
        cursor.execute(query, (user_id,))
        user = cursor.fetchone()

        if user:
            # 이메일 주소 생성
            user['email'] = f"{user['email_id']}@{user['domain']}"

            # 선호 장르 조회
            query_genres = """
            SELECT g.genre_title
            FROM user_pref_genres upg
            JOIN genre g ON upg.genre_id = g.genre_id
            WHERE upg.user_id = %s
            """
            cursor.execute(query_genres, (user_id,))
            genres = cursor.fetchall()

            # 장르를 쉼표로 구분된 문자열로 생성
            user['preferred_genres'] = ", ".join([genre['genre_title'] for genre in genres])

        else:
            flash('사용자 정보를 찾을 수 없습니다.', 'danger')
            return redirect(url_for('recommendations'))

    except mysql.connector.Error as err:
        # 데이터베이스 오류 처리
        flash(f"데이터베이스 오류: {err}", 'danger')
        return redirect(url_for('recommendations'))
    finally:
        # 리소스 정리
        if cursor:
            cursor.close()
        if mydb:
            mydb.close()

    # 템플릿 렌더링
    return render_template('profile.html', user=user)


@app.route('/filter_movies', methods=['GET'])
def filter_movies():
    # 체크박스에서 선택된 장르 가져오기
    selected_genres = request.args.getlist('genre', [])

    # DB 연결
    mydb = mysql.connector.connect(**db_config)
    cursor = mydb.cursor(dictionary=True)

    try:
        if not selected_genres:
            # 선택된 장르가 없을 경우 모든 영화 가져오기
            cursor.execute("SELECT * FROM movie_info")
        else:
            # 선택된 장르에 해당하는 영화만 가져오기
            genre_placeholders = ', '.join(['%s'] * len(selected_genres))
            query = f"SELECT * FROM movie_info WHERE genre IN ({genre_placeholders})"
            cursor.execute(query, selected_genres)

        # 쿼리 결과 가져오기
        filtered_movies = cursor.fetchall()
    except mysql.connector.Error as err:
        # 데이터베이스 오류 처리 
        return jsonify({"error": f"Database error: {err}"}), 500
    finally:
        # 커서와 데이터베이스 연결 닫기
        cursor.close()
        mydb.close()

    # 필터링된 영화 데이터를 JSON 형식으로 반환
    return jsonify(filtered_movies)


#----------------관리자---------------------------------

# 관리자 대시보드 페이지
@app.route('/admin-dashboard')
def admin_dashboard():
    if 'email_id' not in session or session.get('admin_yn') != 'Y':
        flash('관리자 권한이 필요합니다.', 'danger')
        return redirect(url_for('login_user'))
    return render_template('admin_dashboard.html')

@app.route('/add-movie', methods=['GET', 'POST'])
def add_movie():
    if 'email_id' not in session or session.get('admin_yn') != 'Y':
        flash('관리자 권한이 필요합니다.', 'danger')
        return redirect(url_for('login_user'))

    if request.method == 'POST':
        # 영화 등록 처리
        movie_id = request.form.get('movie_id')
        movie_title = request.form.get('movie_title')
        release_year = request.form.get('release_year')
        runtime = request.form.get('runtime')
        watch_grade = request.form.get('watch_grade')
        add_time = request.form.get('add_time')
        end_time = request.form.get('end_time')
        directors = request.form.get('directors').split(',')
        genres = request.form.getlist('genres')
        synopsis = request.form.get('synopsis')
 
        poster = request.files.get('poster_path')
        if poster and poster.filename:
            filename = secure_filename(poster.filename)
            upload_folder = 'img'
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
            poster_path = os.path.join(upload_folder, filename)
            poster.save(poster_path)
        else:
            flash("포스터 이미지를 업로드하세요.", "danger")
            return redirect(request.url)
        
        video = request.files.get('video_path')
        if video and video.filename:
            video_filename = secure_filename(video.filename)
            upload_folder = 'videos'
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
            video_path = os.path.join(upload_folder, video_filename)
            video.save(video_path)
        else:
            video_path = None

        # DB에 영화 정보 저장
        mydb = mysql.connector.connect(**db_config)
        cursor = mydb.cursor()
        cursor.execute(
            "INSERT INTO movie_info (movie_id, poster_path, video_path, movie_title, release_year, runtime, watch_grade, add_time, end_time) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (movie_id, poster_path, video_path, movie_title, release_year, runtime, watch_grade, add_time, end_time)
        )
        
        # 감독 정보 저장
        seq_no = 1
        for director in directors:
            cursor.execute(
                "INSERT INTO movie_director (movie_id, seq_no, director) VALUES (%s, %s, %s)",
                (movie_id, seq_no, director.strip())
            )
            seq_no += 1

        # 장르 정보 저장
        seq_no = 1
        for genre_id in genres:
            cursor.execute(
                "INSERT INTO movie_genre (movie_id, seq_no, genre_id) VALUES (%s, %s, %s)",
                (movie_id, seq_no, genre_id)
            )
            seq_no += 1

        # 줄거리 저장
        cursor.execute(
            "INSERT INTO movie_synopsis (movie_id, synopsis1) VALUES (%s, %s)",
            (movie_id, synopsis)
        )
        mydb.commit()
        cursor.close()
        mydb.close()

        # 사용자 알림 저장
        mydb = mysql.connector.connect(**db_config)
        cursor = mydb.cursor(dictionary=True)  # 딕셔너리 형식으로 데이터 반환

        # 사용자 ID 가져오기
        cursor.execute("SELECT user_id FROM user_info")
        users = cursor.fetchall()  # users는 딕셔너리 리스트로 반환

        for user in users:
            cursor.execute(
                "INSERT INTO announce (user_id, d_date, day_seq_no, movie_id, read_yn) VALUES (%s, %s, %s, %s, %s)",
                (user['user_id'], datetime.now().strftime('%Y%m%d'), 1, movie_id, 'N')  # 딕셔너리 키로 접근
            )
        mydb.commit()
        flash('새로운 영화가 성공적으로 등록되었습니다.', 'success')
        cursor.close()
        mydb.close()

        return redirect(url_for('admin_dashboard'))

    # GET 요청 시 장르 데이터 가져오기
    mydb = mysql.connector.connect(**db_config)
    cursor = mydb.cursor(dictionary=True)
    cursor.execute("SELECT genre_id, genre_title FROM genre")
    genres = cursor.fetchall()
    cursor.close()
    mydb.close()

    return render_template('add_movie.html', genres=genres)

@app.route('/mark-notifications-read', methods=['POST'])
def mark_notifications_read():
    """
    영화 추가 시 알람을 사용자에게 전달하기 위한 라우트.
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session['user_id']
    mydb = mysql.connector.connect(**db_config)
    cursor = mydb.cursor()

    try:
        # 알림 생성 (예시)
        cursor.execute("""
            INSERT INTO announce (user_id, d_date, day_seq_no, movie_id, read_yn)
            VALUES (%s, CURDATE(), %s, %s, 'N')
        """, (user_id, 1, 'MOVIE_ID_PLACEHOLDER'))  # 'MOVIE_ID_PLACEHOLDER'를 실제 영화 ID로 대체
        mydb.commit()

        return jsonify({'success': True, 'message': 'Notification added successfully.'})
    except mysql.connector.Error as e:
        print(f"Database error: {e}")
        return jsonify({'error': 'Database error', 'message': str(e)}), 500
    finally:
        cursor.close()
        mydb.close()

# 영화 관리 페이지
@app.route('/manage-movies', methods=['GET'])
def manage_movies():
    if 'email_id' not in session or session.get('admin_yn') != 'Y':
        flash('관리자 권한이 필요합니다.', 'danger')
        return redirect(url_for('login_user'))

    query = request.args.get('query', '').strip()  # 검색어 가져오기
    mydb = mysql.connector.connect(**db_config)
    cursor = mydb.cursor(dictionary=True)

    try:
        if query:
            search_query = f"%{query}%"
            # 검색 시 유사도를 기반으로 내림차순 정렬
            cursor.execute("""
                SELECT mi.movie_id, mi.movie_title, mi.release_year, md.director, mi.close_time,
                CASE
                    WHEN mi.movie_title LIKE %s THEN 2
                    WHEN md.director LIKE %s THEN 1
                    ELSE 0
                END AS relevance
                FROM movie_info mi
                LEFT JOIN movie_director md ON mi.movie_id = md.movie_id
                WHERE mi.movie_title LIKE %s OR md.director LIKE %s
                ORDER BY relevance DESC, mi.movie_id ASC
            """, (search_query, search_query, search_query, search_query))
        else:
            # 검색어가 없을 경우 전체 영화 ID 기준 오름차순 정렬
            cursor.execute("""
                SELECT mi.movie_id, mi.movie_title, mi.release_year, md.director, mi.close_time
                FROM movie_info mi
                LEFT JOIN movie_director md ON mi.movie_id = md.movie_id
                ORDER BY mi.movie_id ASC
            """)

        movies = cursor.fetchall()
    except mysql.connector.Error as err:
        flash(f"데이터베이스 오류: {err}", 'danger')
        movies = []
    finally:
        cursor.close()
        mydb.close()

    return render_template('manage_movies.html', movies=movies, query=query)

@app.route('/edit-movie/<string:movie_id>', methods=['GET', 'POST'])
def edit_movie(movie_id):
    if 'email_id' not in session or session.get('admin_yn') != 'Y':
        flash('관리자 권한이 필요합니다.', 'danger')
        return redirect(url_for('login_user'))

    mydb = mysql.connector.connect(**db_config)
    cursor = mydb.cursor(dictionary=True)

    if request.method == 'POST':
        # 수정된 데이터 처리
        movie_title = request.form.get('movie_title')
        release_year = request.form.get('release_year')
        watch_grade = request.form.get('watch_grade')
        runtime = request.form.get('runtime')
        add_time = request.form.get('add_time')
        end_time = request.form.get('end_time')
        close_time = request.form.get('close_time')

        actor = request.form.get('actor')
        country = request.form.get('country')
        director = request.form.get('director')
        synopsis1 = request.form.get('synopsis1')
        synopsis2 = request.form.get('synopsis2')
        keyword = request.form.get('keyword')

        # 평점 관련 데이터
        grade_total = float(request.form.get('grade_total', 0))
        grade_count = float(request.form.get('grade_cnt', 0))

        actor_list = [actor.strip() for actor in actor.split(',') if actor.strip()]
        country_list = [country.strip() for country in country.split(',') if country.strip()]
        director_list = [director.strip() for director in director.split(',') if director.strip()]
        keyword_list = [keyword.strip() for keyword in keyword.split(',') if keyword.strip()]

        # 평점 평균 계산
        grade_avg = grade_total / (grade_count if grade_count > 0 else 1)
        rounded_avg = round(grade_avg, 1) if grade_avg is not None else 0

        try:
            # movie_info 업데이트
            cursor.execute("""
                UPDATE movie_info
                SET movie_title = %s,
                    release_year = %s, watch_grade = %s, runtime = %s,
                    add_time = %s, end_time = %s, close_time = %s
                WHERE movie_id = %s
            """, (movie_title, release_year, watch_grade, runtime,
                  add_time, end_time, close_time, movie_id))

            # movie_grade 테이블 업데이트
            cursor.execute("""
                INSERT INTO movie_grade (movie_id, grade_total, grade_cnt, grade_avg)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    grade_total = VALUES(grade_total),
                    grade_cnt = VALUES(grade_cnt),
                    grade_avg = VALUES(grade_avg)
            """, (movie_id, grade_total, grade_count, rounded_avg))

            # movie_actor, movie_country, movie_director, movie_meta 업데이트
            cursor.execute("DELETE FROM movie_actor WHERE movie_id = %s", (movie_id,))
            for seq_no, actor in enumerate(actor_list, start=1):
                cursor.execute("""
                    INSERT INTO movie_actor (movie_id, seq_no, actor) 
                    VALUES (%s, %s, %s)
                """, (movie_id, seq_no, actor))

            cursor.execute("DELETE FROM movie_country WHERE movie_id = %s", (movie_id,))
            for seq_no, country in enumerate(country_list, start=1):
                cursor.execute("""
                    INSERT INTO movie_country (movie_id, seq_no, country) 
                    VALUES (%s, %s, %s)
                """, (movie_id, seq_no, country))

            cursor.execute("DELETE FROM movie_director WHERE movie_id = %s", (movie_id,))
            for seq_no, director in enumerate(director_list, start=1):
                cursor.execute("""
                    INSERT INTO movie_director (movie_id, seq_no, director) 
                    VALUES (%s, %s, %s)
                """, (movie_id, seq_no, director))

            cursor.execute("DELETE FROM movie_meta WHERE movie_id = %s", (movie_id,))
            for seq_no, keyword in enumerate(keyword_list, start=1):
                cursor.execute("""
                    INSERT INTO movie_meta (movie_id, seq_no, keyword) 
                    VALUES (%s, %s, %s)
                """, (movie_id, seq_no, keyword))

            # movie_synopsis 업데이트
            cursor.execute("""
                UPDATE movie_synopsis
                SET synopsis1 = %s, synopsis2 = %s
                WHERE movie_id = %s
            """, (synopsis1, synopsis2, movie_id))

            mydb.commit()
            flash('영화 정보가 성공적으로 수정되었습니다.', 'success')
        except mysql.connector.Error as err:
            flash(f"데이터베이스 오류: {err}", 'danger')
        finally:
            cursor.close()
            mydb.close()
            return redirect(url_for('manage_movies'))

    # 기존 영화 정보 불러오기
    cursor.execute("SELECT * FROM movie_info WHERE movie_id = %s", (movie_id,))
    movie_info = cursor.fetchone()

    if not movie_info:
        flash('영화를 찾을 수 없습니다.', 'danger')
        cursor.close()
        mydb.close()
        return redirect(url_for('manage_movies'))

    cursor.execute("SELECT actor FROM movie_actor WHERE movie_id = %s", (movie_id,))
    movie_actors = cursor.fetchall()
    movie_actor = ', '.join([actor['actor'] for actor in movie_actors]) if movie_actors else ''

    cursor.execute("SELECT country FROM movie_country WHERE movie_id = %s", (movie_id,))
    movie_countries = cursor.fetchall()
    movie_country = ', '.join([country['country'] for country in movie_countries]) if movie_countries else ''

    cursor.execute("SELECT director FROM movie_director WHERE movie_id = %s", (movie_id,))
    movie_directors = cursor.fetchall()
    movie_director = ', '.join([director['director'] for director in movie_directors]) if movie_directors else ''

    cursor.execute("SELECT synopsis1, synopsis2 FROM movie_synopsis WHERE movie_id = %s", (movie_id,))
    movie_synopsis = cursor.fetchone()

    cursor.execute("SELECT keyword FROM movie_meta WHERE movie_id = %s", (movie_id,))
    movie_keywords = cursor.fetchall()
    movie_meta = ', '.join([keyword['keyword'] for keyword in movie_keywords]) if movie_keywords else ''

    cursor.execute("SELECT grade_total, grade_cnt FROM movie_grade WHERE movie_id = %s", (movie_id,))
    movie_grade = cursor.fetchone()

    if movie_grade:
        grade_total = movie_grade['grade_total'] if movie_grade['grade_total'] is not None else 0
        grade_count = movie_grade['grade_cnt'] if movie_grade['grade_cnt'] is not None else 0
    else:
        grade_total = 0
        grade_count = 0

    cursor.close()
    mydb.close()

    return render_template(
        'edit_movie.html',
        movie_info=movie_info,
        movie_actor=movie_actor,
        movie_country=movie_country,
        movie_director=movie_director,
        movie_synopsis=movie_synopsis or {},
        movie_meta=movie_meta,
        grade_total=grade_total,  # 평점 합
        grade_count=grade_count  # 평점 인원
    )



# 영화 숨김 라우트
@app.route('/hide-movie/<string:movie_id>', methods=['GET'])
def hide_movie(movie_id):
    if 'email_id' not in session or session.get('admin_yn') != 'Y':
        flash('관리자 권한이 필요합니다.', 'danger')
        return redirect(url_for('login_user'))

    mydb = mysql.connector.connect(**db_config)
    cursor = mydb.cursor()

    try:
        # 오늘 날짜를 yyyymmdd 형식으로 저장
        today_date = datetime.now().strftime('%Y%m%d')

        # close_time 업데이트
        cursor.execute("""
            UPDATE movie_info
            SET close_time = %s
            WHERE movie_id = %s
        """, (today_date, movie_id))

        mydb.commit()
        flash('영화가 성공적으로 숨겨졌습니다.', 'success')
    except mysql.connector.Error as err:
        flash(f"영화 숨김 처리 중 오류가 발생했습니다: {err}", 'danger')
    finally:
        cursor.close()
        mydb.close()

    return redirect(url_for('manage_movies'))

@app.route('/unhide-movie/<string:movie_id>', methods=['GET'])
def unhide_movie(movie_id):
    if 'email_id' not in session or session.get('admin_yn') != 'Y':
        flash('관리자 권한이 필요합니다.', 'danger')
        return redirect(url_for('login_user'))

    mydb = mysql.connector.connect(**db_config)
    cursor = mydb.cursor()
    try:
        cursor.execute("""
            UPDATE movie_info
            SET close_time = NULL
            WHERE movie_id = %s
        """, (movie_id,))
        mydb.commit()
        flash('영화가 공개되었습니다.', 'success')
    except mysql.connector.Error as err:
        flash(f"데이터베이스 오류: {err}", 'danger')
    finally:
        cursor.close()
        mydb.close()

    return redirect(url_for('manage_movies'))

# 계약 관리 페이지
@app.route('/manage-expiring-movies', methods=['GET'])
def manage_expiring_movies():
    if 'email_id' not in session or session.get('admin_yn') != 'Y':
        flash('관리자 권한이 필요합니다.', 'danger')
        return redirect(url_for('login_user'))
    
    query = request.args.get('query', '').strip()  # 검색어 가져오기
    mydb = mysql.connector.connect(**db_config)
    cursor = mydb.cursor(dictionary=True)

    try:
        # 오늘 날짜 및 임박한 계약 종료일 계산
        today = datetime.today().strftime('%Y%m%d')
        near_expiry_date = (datetime.today() + timedelta(days=30)).strftime('%Y%m%d')
    
        if query:
            search_query = f"%{query}%"
            # 검색 시 유사도를 기반으로 내림차순 정렬
            cursor.execute("""
                SELECT movie_id, movie_title, release_year, end_time
                FROM movie_info
                WHERE end_time BETWEEN %s AND %s
                AND (movie_title LIKE %s)  -- 제목으로 검색
                ORDER BY 
                    CASE 
                        WHEN movie_title LIKE %s THEN 1  -- 제목이 정확히 일치하는 경우
                        WHEN movie_title LIKE %s THEN 2  -- 제목에 포함된 경우
                        ELSE 3  -- 그 외의 경우
                    END,
                    end_time ASC  -- 계약 종료일 기준으로 정렬
            """, (today, near_expiry_date, search_query, search_query, search_query))
        else:
            # 계약 종료일이 가까운 영화 조회
            cursor.execute("""
                SELECT movie_id, movie_title, release_year, end_time 
                FROM movie_info 
                WHERE end_time BETWEEN %s AND %s
                
                ORDER BY end_time ASC
            """, (today, near_expiry_date))

        expiring_movies = cursor.fetchall()
    except mysql.connector.Error as err:
        flash(f"데이터베이스 오류: {err}", 'danger')
        expiring_movies = []
    finally:
        cursor.close()
        mydb.close()

    return render_template('manage_expiring_movies.html', expiring_movies=expiring_movies)


# ## log 데이터
# # 로그 기록을 위한 함수
# def get_db():
#     return mysql.connector.connect(**db_config)

# from datetime import datetime  # datetime 모듈에서 datetime 클래스만 가져오기
# def log_request(user_id, method, path, status_code):
#     mydb = mysql.connector.connect(**db_config)
#     cursor = mydb.cursor()
#     timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#     cursor.execute(
#         "INSERT INTO origin_logs (ip_address, user_id, timestamp, request_info, status_code) VALUES (%s, %s, %s, %s, %s)",
#         (request.remote_addr, user_id, timestamp, f"{method} {path}", status_code)
#     )
#     mydb.commit()
#     cursor.close()
#     mydb.close()

# @app.before_request
# def log_request():
#     user_id = session.get('user_id')  # 세션에서 사용자 ID를 가져옴
#     ip_address = request.remote_addr
#     timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#     request_info = f"{request.method} {request.path}"
    
#     # 상태 코드는 요청 처리 후 결정되므로, 후속 요청 처리에서 저장
#     g.log_data = (ip_address, user_id, timestamp, request_info)

# @app.after_request
# def log_response(response):
#     ip_address, user_id, timestamp, request_info = g.log_data
#     status_code = response.status_code
    
#     # 데이터베이스에 로그 저장
#     db = get_db()
#     cursor = db.cursor()
#     query = "INSERT INTO origin_logs (ip_address, user_id, timestamp, request_info, status_code) VALUES (%s, %s, %s, %s, %s)"
#     cursor.execute(query, (ip_address, user_id, timestamp, request_info, status_code))
#     db.commit()
#     cursor.close()
#     db.close()

#     return response

def create_admin_account():
    # 관리자 계정 정보
    admin_email = "admin@example.com"  # 관리자 이메일 (수정 가능)
    admin_password = "admin_password"  # 관리자 비밀번호 (수정 가능)
    # 비밀번호 해싱: bcrypt 사용
    hashed_password = bcrypt.hashpw(admin_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


    # 이메일 분리
    admin_email_parts = admin_email.split('@')
    admin_email_id = admin_email_parts[0]
    admin_domain = admin_email_parts[1]

    # DB 연결 및 관리자 계정 추가
    try:
        mydb = mysql.connector.connect(**db_config)
        cursor = mydb.cursor(dictionary=True)

        # 이메일 중복 확인
        cursor.execute("SELECT * FROM user_info WHERE email_id = %s AND domain = %s", (admin_email_id, admin_domain))
        existing_user = cursor.fetchone()

        if existing_user:
            print("이미 사용 중인 이메일입니다. 다른 이메일을 사용하세요.")
        else:
            # 관리자 계정 추가
            cursor.execute(
                "INSERT INTO user_info (user_name, email_id, domain, user_pwd, province, gender, date_of_birth, new_user_yn, admin_yn, retry_cnt, temp_pw_yn) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                ("0000000", admin_email_id, admin_domain, hashed_password, 'N/A', 'N', '19700101', 'N', 'Y', 0, 'N')
            )

            mydb.commit()
            print("관리자 계정이 생성되었습니다.")
    except mysql.connector.Error as err:
        print(f"관리자 계정 생성 중 오류가 발생했습니다: {err}")
    finally:
        cursor.close()
        mydb.close()

if __name__ == '__main__':
    # create_admin_account()
    app.run(debug=True)
