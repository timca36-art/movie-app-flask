from flask import Flask, render_template, request, redirect, session, flash
import requests
import math
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'e6bacee0-6cc9-4ef0-b0de-0900ec8ace7c'    # Замените на свой

KINOPOISK_API_KEY = 'e6bacee0-6cc9-4ef0-b0de-0900ec8ace7c'

HEADERS = {
    'X-API-KEY': KINOPOISK_API_KEY,
    'Content-Type': 'application/json'
}
PER_PAGE = 15

def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT)''')
    conn.commit()
    conn.close()

    conn = sqlite3.connect('comments.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS comments
                 (id INTEGER PRIMARY KEY, film_id INTEGER, text TEXT, author TEXT, date TEXT)''')
    conn.commit()
    conn.close()

    conn = sqlite3.connect('user_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS history
                 (id INTEGER PRIMARY KEY, user_id INTEGER, film_id INTEGER, date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS favorites
                 (id INTEGER PRIMARY KEY, user_id INTEGER, film_id INTEGER)''')
    conn.commit()
    conn.close()

init_db()

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password)

        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
            conn.commit()
            flash('Регистрация успешна! Войдите.', 'success')
            return redirect('/login')
        except sqlite3.IntegrityError:
            flash('Пользователь уже существует.', 'error')
        conn.close()
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT id, password FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[1], password):
            session['user_id'] = user[0]
            session['user'] = username
            flash('Вход успешный!', 'success')
            return redirect('/')
        else:
            flash('Неверный логин или пароль.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('user', None)
    flash('Вы вышли.', 'success')
    return redirect('/')

@app.route('/')
def index():
    search = request.args.get('search', '').strip()
    genre_id = request.args.get('genre_id', '')
    page = max(1, request.args.get('page', 1, type=int))

    films = []
    total_pages = 1

    genres_url = 'https://kinopoiskapiunofficial.tech/api/v2.2/films/filters'
    g = requests.get(genres_url, headers=HEADERS)
    genres = g.json().get('genres', []) if g.status_code == 200 else []

    url = f'https://kinopoiskapiunofficial.tech/api/v2.2/films/top?type=TOP_250_BEST_FILMS&page={page}'
    if search:
        url = f'https://kinopoiskapiunofficial.tech/api/v2.1/films/search-by-keyword?keyword={search}&page={page}'
    elif genre_id:
        url = f'https://kinopoiskapiunofficial.tech/api/v2.1/films/search-by-filters?genre={genre_id}&page={page}'

    r = requests.get(url, headers=HEADERS)
    data = r.json()
    if 'films' in data:
        films = data['films'][:PER_PAGE]
        total = 250
    elif 'searchFilms' in data:
        films = data['searchFilms'][:PER_PAGE]
        total = data.get('searchFilmsCount', 0)
    else:
        films = []
        total = 0
    total_pages = math.ceil(total / PER_PAGE)

    return render_template('index.html', films=films, page=page, total_pages=total_pages, genres=genres, search=search, genre_id=genre_id)

@app.route('/film/<int:film_id>', methods=['GET', 'POST'])
def film_detail(film_id):
    url = f'https://kinopoiskapiunofficial.tech/api/v2.2/films/{film_id}'
    film = requests.get(url, headers=HEADERS).json()

    # Отзывы из Кинопоиска (вернули)
    rev = requests.get(f'https://kinopoiskapiunofficial.tech/api/v1/reviews?filmId={film_id}&page=1', headers=HEADERS).json()
    reviews = rev.get('reviews', [])[:5]

    img = requests.get(f'https://kinopoiskapiunofficial.tech/api/v2.2/films/{film_id}/images?type=STILL&page=1', headers=HEADERS).json()
    images = img.get('items', [])
    poster = images[0]['imageUrl'] if images else ''
    backdrop = images[1]['imageUrl'] if len(images) > 1 else poster

    conn = sqlite3.connect('comments.db')
    c = conn.cursor()
    c.execute("SELECT text, author, date FROM comments WHERE film_id=?", (film_id,))
    comments = c.fetchall()
    conn.close()

    if request.method == 'POST':
        text = request.form.get('text')
        author = session.get('user', request.form.get('author', 'Аноним'))
        date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if text:
            conn = sqlite3.connect('comments.db')
            c = conn.cursor()
            c.execute("INSERT INTO comments (film_id, text, author, date) VALUES (?, ?, ?, ?)", (film_id, text, author, date))
            conn.commit()
            conn.close()
        return redirect(f'/film/{film_id}')

    is_favorite = False
    if 'user_id' in session:
        conn = sqlite3.connect('user_data.db')
        c = conn.cursor()
        c.execute("SELECT id FROM favorites WHERE user_id = ? AND film_id = ?", (session['user_id'], film_id))
        if c.fetchone():
            is_favorite = True
        # История просмотра
        c.execute("SELECT id FROM history WHERE user_id = ? AND film_id = ?", (session['user_id'], film_id))
        if not c.fetchone():
            date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute("INSERT INTO history (user_id, film_id, date) VALUES (?, ?, ?)", (session['user_id'], film_id, date))
        conn.commit()
        conn.close()

    return render_template('film.html', film=film, reviews=reviews, poster=poster, backdrop=backdrop, comments=comments, is_favorite=is_favorite)

@app.route('/add_favorite/<int:film_id>')
def add_favorite(film_id):
    if 'user_id' in session:
        conn = sqlite3.connect('user_data.db')
        c = conn.cursor()
        c.execute("SELECT id FROM favorites WHERE user_id = ? AND film_id = ?", (session['user_id'], film_id))
        if not c.fetchone():
            c.execute("INSERT INTO favorites (user_id, film_id) VALUES (?, ?)", (session['user_id'], film_id))
            flash('Добавлено в избранное.', 'success')
        else:
            c.execute("DELETE FROM favorites WHERE user_id = ? AND film_id = ?", (session['user_id'], film_id))
            flash('Удалено из избранного.', 'success')
        conn.commit()
        conn.close()
    else:
        flash('Войдите для добавления в избранное.', 'error')
    return redirect(f'/film/{film_id}')

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        flash('Войдите для просмотра профиля.', 'error')
        return redirect('/login')

    conn = sqlite3.connect('user_data.db')
    c = conn.cursor()
    c.execute("SELECT film_id, date FROM history WHERE user_id = ? ORDER BY date DESC", (session['user_id'],))
    history = c.fetchall()

    c.execute("SELECT film_id FROM favorites WHERE user_id = ?", (session['user_id'],))
    favorites = c.fetchall()
    conn.close()

    history_films = []
    for h in history:
        url = f'https://kinopoiskapiunofficial.tech/api/v2.2/films/{h[0]}'
        r = requests.get(url, headers=HEADERS)
        film = r.json()
        history_films.append({'film': film, 'date': h[1]})

    favorites_films = []
    for f in favorites:
        url = f'https://kinopoiskapiunofficial.tech/api/v2.2/films/{f[0]}'
        r = requests.get(url, headers=HEADERS)
        film = r.json()
        favorites_films.append(film)

    return render_template('profile.html', history=history_films, favorites=favorites_films)

if __name__ == '__main__':
    app.run(debug=True)