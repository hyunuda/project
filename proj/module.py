import mysql.connector
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import CountVectorizer



# MySQL 설정
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '@mysql123',
    'database': 'movie_recommendations'
}

#user_id = 15

def fetch_user_genres_and_movies(user_id):
    """
    MySQL에서 사용자 선호 장르와 영화 데이터를 가져오는 함수
    """
    conn = None  # 기본값으로 초기화
    try:
        # MySQL 데이터베이스 연결
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        # 사용자 선호 장르ID 가져오기
        cursor.execute(f"""
            SELECT genre_id 
            FROM user_pref_genres 
            WHERE user_id = {user_id}
        """)
        user_genres_id = [row[0] for row in cursor.fetchall()]

        if not user_genres_id:
            print("사용자의 선호 장르가 없습니다.")
            return [], []

        # 리스트를 SQL 쿼리에서 사용할 수 있도록 따옴표로 감싸기
        user_genres_id_str = ', '.join(f"'{genre_id}'" for genre_id in user_genres_id)

        # 영화 정보와 장르를 JOIN하여 가져오기 (평점 내림차순 정렬)
        cursor.execute(f"""
            SELECT mi.movie_id, mi.movie_title, mi.watch_grade, mi.release_year, mg.genre_id
            FROM movie_info mi
            JOIN movie_genre mg ON mi.movie_id = mg.movie_id
            JOIN movie_grade mgr ON mi.movie_id = mgr.movie_id
            WHERE mg.genre_id IN ({user_genres_id_str})
            AND mgr.grade_cnt >= 5
            ORDER BY mgr.grade_avg DESC
        """)
        movies = cursor.fetchall()

        return user_genres_id, movies

    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return [], []

    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def recommend_newbie_movies(user_id):
    """
    사용자 선호 장르에 맞는 영화를 추천하는 함수
    """
    # MySQL 데이터 가져오기
    user_genres, movies = fetch_user_genres_and_movies(user_id)

    if not movies:
        print("추천할 영화를 찾을 수 없습니다.")
        return

    # 영화 데이터프레임 생성
    movies_df = pd.DataFrame(movies, columns=['movieID', 'title', 'score', 'year', 'genreID'])

    # 중복 제거 (동일 영화에 여러 장르가 있을 수 있음)
    recommended_movies_df = movies_df.drop_duplicates(subset=['movieID'])

    # 추천 영화 출력
    # print("사용자 선호 장르에 맞는 추천 영화:")
    # print(recommended_movies_df.head(20))  # 상위 20개 출력
    return recommended_movies_df.head(20)

# 영화 추천 실행
# recommend_newbie_movies(4)

def fetch_user_data(user_id):
    """
    사용자 시청 이력 및 영화 DB 데이터를 가져오는 함수
    """
    try:
        # MySQL 연결
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        # 사용자 시청 이력 데이터 가져오기
        cursor.execute(f"""
            SELECT uwl.d_date, uwl.day_seq_no, uwl.movie_id, uwl.watch_per,
                GROUP_CONCAT(DISTINCT g.genre_title SEPARATOR ', ') AS genre_title,
                GROUP_CONCAT(DISTINCT mm.keyword SEPARATOR ', ') AS keyword
            FROM user_watched_log uwl
            JOIN movie_genre mg ON uwl.movie_id = mg.movie_id
            JOIN genre g ON mg.genre_id = g.genre_id
            JOIN movie_meta mm ON uwl.movie_id = mm.movie_id
            WHERE user_id = {user_id}
            AND watch_per >= 80
            GROUP BY uwl.d_date, uwl.day_seq_no, uwl.movie_id, uwl.watch_per
            ORDER BY uwl.d_date DESC, uwl.day_seq_no ASC
        """)
        user_watched_log = cursor.fetchall()

        # 전체 영화 DB 데이터 가져오기
        cursor.execute("""
            SELECT mi.movie_id, mi.movie_title,
                GROUP_CONCAT(DISTINCT g.genre_title SEPARATOR ', ') AS genre_title,
                GROUP_CONCAT(DISTINCT mm.keyword SEPARATOR ', ') AS keyword
            FROM movie_info mi
            JOIN movie_genre mg ON mi.movie_id = mg.movie_id
            JOIN genre g ON mg.genre_id = g.genre_id
            JOIN movie_meta mm ON mi.movie_id = mm.movie_id
            GROUP BY mi.movie_id, mi.movie_title
        """)
        movie_db = cursor.fetchall()

        print("시청이력 ")
        return user_watched_log, movie_db

    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return [], []

    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()


def recommend_oldbie_movies(user_id):
    # 1. 사용자 시청 이력과 영화 DB 가져오기
    user_watched_log, movie_db = fetch_user_data(user_id)

    # 2. 사용자 데이터 및 영화 DB를 DataFrame으로 변환
    user_df = pd.DataFrame(user_watched_log, columns=['d_date', 'day_seq_no', 'movie_id', 'watch_per', 'genre_title', 'keyword'])
    movies_df = pd.DataFrame(movie_db, columns=['movie_id', 'movie_title', 'genre_title', 'keyword'])


    # 3. 사용자 장르와 키워드 데이터를 연결하여 하나의 문자열로 결합(중복제거)
    user_genres = ' '.join(user_df['genre_title'].unique())
    user_keywords = ' '.join(user_df['keyword'].unique())
    # user_genres = ' '.join(' '.join(user_df['genre']).split())
    # user_keywords = ' '.join(' '.join(user_df['keyword']).split())
    user_genres_series = pd.Series([user_genres])
    user_keywords_series = pd.Series([user_keywords])

    movies_df['genre_title'] = movies_df['genre_title'].str.replace(',', '', regex = False)
    movies_df['keyword'] = movies_df['keyword'].str.replace(',', '', regex = False)

    # 사용자 장르와 DB 장르를 결합
    genres_concat = pd.concat([user_genres_series, movies_df['genre_title']], ignore_index=True)
    keywords_concat = pd.concat([user_keywords_series, movies_df['keyword']], ignore_index=True)
    genres_concat = genres_concat.drop(index=1).reset_index(drop=True)
    keywords_concat = keywords_concat.drop(index=1).reset_index(drop=True)


    # CountVectorizer를 사용한 벡터화
    vectorizer_genre = CountVectorizer()
    vectorizer_keyword = CountVectorizer(ngram_range = (1,3))

    # 장르 벡터화 및 유사도 계산
    genre_vectors = vectorizer_genre.fit_transform(genres_concat)
    genre_similarity = cosine_similarity(genre_vectors)

    # 키워드 벡터화 및 유사도 계산
    keyword_vectors = vectorizer_keyword.fit_transform(keywords_concat)
    keyword_similarity = cosine_similarity(keyword_vectors)


    # 사용자와 영화 DB 간의 유사도 추출 (장르와 키워드)
    user_index = 0
    genre_similarity_scores = genre_similarity[user_index][1:]  # 사용자 데이터 제외
    keyword_similarity_scores = keyword_similarity[user_index][1:]

    # 최종 유사도 계산 (가중치 적용)
    weights = {'genre': 0.4, 'keyword': 0.6}
    final_similarity_scores = (weights['genre'] * genre_similarity_scores +
                            weights['keyword'] * keyword_similarity_scores)
    

    # 유사도 점수에 따라 영화 정렬
    movies_df['similarity_score'] = pd.Series([0] + list(final_similarity_scores))  # 사용자 데이터는 0으로 설정
    recommended_movies = movies_df[1:].sort_values(by='similarity_score', ascending=False)  # 사용자 데이터 제외

    # 사용자 영화 제거
    recommended_movies = recommended_movies[~recommended_movies['movie_id'].isin(user_df['movie_id'])]

    # 추천 결과 출력(20개)
    return recommended_movies[['movie_id', 'movie_title', 'genre_title', 'similarity_score']].head(20)


