from flask import Flask, render_template, request, redirect, url_for, Blueprint, flash, session, jsonify
from flask_mysqldb import MySQL
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os

app = Flask(__name__)
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = '123456789'
app.config['MYSQL_DB'] = 'webdata_test'

mysql = MySQL(app)
app.secret_key = os.urandom(24)

bp = Blueprint('auth', __name__, url_prefix='/auth', template_folder='templates/auth')
bp_permpanel = Blueprint('permpanel', __name__, url_prefix='/permpanel')

def boss_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session['user_perm'] != 'boss':
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session['user_perm'] not in ['admin', 'boss']:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def user_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session['user_perm'] != 'user':
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/add', methods=['GET', 'POST'])
@admin_required
def add_meeting():
    if request.method == 'POST':
        meeting_name = request.form['meeting_name']
        location = request.form['location']
        if location == 'other':
            location = request.form['otherLocation']
        participants = request.form['participants']  # Bu satır değişti
        meeting_date = datetime.strptime(request.form['meeting_date'], '%Y-%m-%dT%H:%M')
        description = request.form['description']

        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO meetings (meeting_name, location, participants, meeting_date, description) VALUES (%s, %s, %s, %s, %s)",
                    (meeting_name, location, participants, meeting_date, description))
        mysql.connection.commit()
        cur.close()

        return redirect(url_for('index'))

    return render_template('add.html')

@app.route('/delete/<int:id>', methods=['POST'])
@admin_required
def delete_meeting(id):
    cur = mysql.connection.cursor()
    
    # Toplantıyı veritabanından sil
    cur.execute("DELETE FROM meetings WHERE id = %s", (id,))
    mysql.connection.commit()
    cur.close()

    return redirect(url_for('index'))

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_meeting(id):
    cur = mysql.connection.cursor()
    
    if request.method == 'POST':
        meeting_name = request.form['meeting_name']
        location = request.form['location']
        if location == 'other':
            location = request.form['otherLocation']
        participants = request.form['participants']
        meeting_date = datetime.strptime(request.form['meeting_date'], '%Y-%m-%dT%H:%M')
        description = request.form['description']

        cur.execute("UPDATE meetings SET meeting_name=%s, location=%s, participants=%s, meeting_date=%s, description=%s WHERE id=%s",
                    (meeting_name, location, participants, meeting_date, description, id))
        mysql.connection.commit()
        cur.close()

        return redirect(url_for('index'))
    
    else:  # GET isteği
        cur.execute("SELECT * FROM meetings WHERE id = %s", (id,))
        meeting_tuple = cur.fetchone()
        
        if meeting_tuple:
            meeting = {
                'id': meeting_tuple[0],
                'meeting_name': meeting_tuple[1],
                'location': meeting_tuple[2],
                'participants': meeting_tuple[3],
                'meeting_date': meeting_tuple[4],
                'description': meeting_tuple[5]
            }
            cur.close()
            return render_template('edit.html', meeting=meeting)
        else:
            cur.close()
            flash('Toplantı bulunamadı', 'error')
            return redirect(url_for('index'))

# cursor oluşturma yöntemi
@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM users WHERE username = %s OR email = %s", (username, email))
        user = cursor.fetchone()
        if user:
            flash('Bu kullanıcı adı veya e-posta zaten kullanılıyor.', 'danger')
            return redirect(url_for('auth.register'))

        # şifrenin hashlenmesi
        hashed_password = generate_password_hash(password)

        # user verilerinin kaydedilmesi
        cursor.execute("INSERT INTO users (username, email, password) VALUES (%s, %s, %s)", (username, email, hashed_password))
        mysql.connection.commit()
        cursor.close()

        flash('Kayıt başarıyla tamamlandı. Giriş yapabilirsiniz.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()

        if user and check_password_hash(user[3], password):
            session['user_id'] = user[0]
            session['user_perm'] = user[5]  # user_perm değerini session içine ekleme
            flash('Başarıyla giriş yaptınız.', 'success')
            return redirect(url_for('index'))
        else:
            flash('Geçersiz kullanıcı adı veya şifre.', 'danger')

    return render_template('auth/login.html')

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
@login_required
def index():
    remove_past_meetings()  # Geçmiş toplantıları sil

    cur = mysql.connection.cursor()  # mysql.connection üzerinden cursor
    cur.execute("SELECT * FROM meetings ORDER BY meeting_date ASC")
    meetings = cur.fetchall()
    cur.close()

    user_perm = session['user_perm']  # session içindeki user_perm değerini alma

    if user_perm == 'user':
        return render_template('index.html', meetings=meetings)
    elif user_perm == 'admin':
        return render_template('index.html', meetings=meetings, can_edit=True, can_add=True)
    else:
        return render_template('index.html', meetings=meetings, can_edit=True, can_add=True, can_manage_perms=True)

@bp_permpanel.route('/', methods=['GET', 'POST'])
@boss_required
def permpanel():
    if request.method == 'POST':
        user_id = request.form['user_id']
        new_perm = request.form['new_perm']
        cursor = mysql.connection.cursor()
        cursor.execute("UPDATE users SET perm = %s WHERE id = %s", (new_perm, user_id))
        mysql.connection.commit()
        cursor.close()
        flash('Yetki güncellendi.', 'success')
        return redirect(url_for('permpanel.permpanel'))

    cursor = mysql.connection.cursor()
    cursor.execute("SELECT id, username, perm FROM users")
    users = cursor.fetchall()
    cursor.close()
    return render_template('permpanel.html', users=users)

@bp_permpanel.route('/delete/<int:user_id>', methods=['POST'])
@boss_required
def delete_user(user_id):
    cursor = mysql.connection.cursor()
    cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
    mysql.connection.commit()
    cursor.close()
    flash('Kullanıcı silindi.', 'success')
    return redirect(url_for('permpanel.permpanel'))

@bp.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('user_perm', None)
    flash('Başarıyla çıkış yaptınız.', 'success')
    return redirect(url_for('auth.login'))

@app.route('/search_emails', methods=['GET'])
@login_required
def search_emails():
    query = request.args.get('q', '')  # URL parametresinden 'q' al
    cur = mysql.connection.cursor()
    cur.execute("SELECT email FROM mails WHERE email LIKE %s", ('%' + query + '%',))
    emails = cur.fetchall()
    cur.close()

    email_list = [email[0] for email in emails]
    return jsonify(email_list)

def remove_past_meetings():
    threshold_date = datetime.now() - timedelta(days=2)
    formatted_threshold_date = threshold_date.strftime('%Y-%m-%d %H:%M:%S')

    cur = mysql.connection.cursor()
    
    # Eski toplantıları old_meetings tablosuna taşı
    cur.execute("""
        INSERT INTO old_meetings (meeting_name, location, participants, meeting_date, description, deleted_at)
        SELECT meeting_name, location, participants, meeting_date, description, NOW()
        FROM meetings
        WHERE meeting_date < %s
    """, (formatted_threshold_date,))
    
    # Eski toplantıları meetings tablosundan sil
    cur.execute("DELETE FROM meetings WHERE meeting_date < %s", (formatted_threshold_date,))
    
    mysql.connection.commit()
    cur.close()
    
@app.route('/old_meetings', methods=['GET'])
@admin_required
def old_meetings():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM old_meetings ORDER BY deleted_at DESC")
    meetings = cur.fetchall()
    cur.close()
    return render_template('old_meetings.html', meetings=meetings)


app.register_blueprint(bp)
app.register_blueprint(bp_permpanel)

if __name__ == '__main__':
    app.run(debug=True)
