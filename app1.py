from flask import Flask, render_template, request, redirect, session
import mysql.connector
import bcrypt
from datetime import datetime

app = Flask(__name__)
app.secret_key = "replace_with_secure_random_string"

# DB — change password if needed
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Raghavendra9",
    database="expense_tracker",
    auth_plugin='mysql_native_password'
)
cursor = db.cursor(dictionary=True)

# default categories for new users
DEFAULT_CATEGORIES = [
    "Food", "Housing", "Transportation", "Current Bill",
    "Water Bill", "Personal Spending"
]

def create_default_categories(uid):
    for c in DEFAULT_CATEGORIES:
        cursor.execute(
            "INSERT INTO categories (user_id, category_name, budget, total_expense) VALUES (%s,%s,0,0)",
            (uid, c)
        )
    db.commit()

@app.route('/')
def index():
    return redirect('/login')

# signup
@app.route('/signup', methods=['GET','POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
        if cursor.fetchone():
            return render_template('signup.html', error="Username already exists")
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
        cursor.execute("INSERT INTO users (username, password) VALUES (%s,%s)", (username, hashed))
        db.commit()
        cursor.execute("SELECT user_id FROM users WHERE username=%s", (username,))
        uid = cursor.fetchone()['user_id']
        create_default_categories(uid)
        return redirect('/login')
    return render_template('signup.html')

# login
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cursor.fetchone()
        if user and bcrypt.checkpw(password.encode(), user['password'].encode()):
            session['user_id'] = user['user_id']
            session['username'] = user['username']
            return redirect('/home')
        return render_template('login.html', error="Invalid username or password")
    return render_template('login.html')

# logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# update income
@app.route('/update_income', methods=['POST'])
def update_income():
    if 'user_id' not in session:
        return redirect('/login')
    uid = session['user_id']
    try:
        new_income = float(request.form.get('new_income') or 0)
    except:
        new_income = 0.0
    cursor.execute("UPDATE users SET total_income=%s WHERE user_id=%s", (new_income, uid))
    db.commit()
    return redirect('/home')

# add budget page (GET shows form; POST updates)
@app.route('/add_budget', methods=['GET','POST'])
def add_budget():
    if 'user_id' not in session:
        return redirect('/login')
    uid = session['user_id']
    if request.method == 'POST':
        cid = request.form['category_id']
        budget = float(request.form['budget'])
        cursor.execute("UPDATE categories SET budget=%s WHERE category_id=%s AND user_id=%s",
                       (budget, cid, uid))
        db.commit()
        return redirect('/add_budget')
    # GET: show categories
    cursor.execute("SELECT * FROM categories WHERE user_id=%s", (uid,))
    categories = cursor.fetchall()
    return render_template('add_budget.html', categories=categories, username=session['username'])

# manage expenses (add + list + edit via modal handled by edit_expense route)
@app.route('/manage_expenses', methods=['GET','POST'])
def manage_expenses():
    if 'user_id' not in session:
        return redirect('/login')
    uid = session['user_id']
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            cid = request.form['category_id']
            amount = float(request.form['amount'])
            date = request.form.get('date') or datetime.today().strftime('%Y-%m-%d')
            cursor.execute("INSERT INTO expenses (user_id, category_id, amount, date) VALUES (%s,%s,%s,%s)",
                           (uid, cid, amount, date))
            cursor.execute("UPDATE categories SET total_expense = total_expense + %s WHERE category_id=%s AND user_id=%s",
                           (amount, cid, uid))
            db.commit()
            return redirect('/manage_expenses')
    # GET: list expenses (joined with category name)
    cursor.execute("""
        SELECT e.expense_id, e.user_id, e.category_id, e.amount, e.date, c.category_name
        FROM expenses e
        JOIN categories c ON e.category_id = c.category_id
        WHERE e.user_id=%s
        ORDER BY e.date DESC
    """, (uid,))
    expenses = cursor.fetchall()
    cursor.execute("SELECT * FROM categories WHERE user_id=%s", (uid,))
    categories = cursor.fetchall()
    return render_template('manage_expenses.html', expenses=expenses, categories=categories, username=session['username'])

# edit expense (POST from modal)
@app.route('/edit_expense', methods=['POST'])
def edit_expense():
    if 'user_id' not in session:
        return redirect('/login')
    uid = session['user_id']
    eid = request.form['expense_id']
    new_amount = float(request.form['amount'])
    new_date = request.form['date']
    # get old
    cursor.execute("SELECT category_id, amount FROM expenses WHERE expense_id=%s AND user_id=%s", (eid, uid))
    old = cursor.fetchone()
    if not old:
        return redirect('/manage_expenses')
    old_amount = float(old['amount'])
    cid = old['category_id']
    cursor.execute("UPDATE expenses SET amount=%s, date=%s WHERE expense_id=%s AND user_id=%s",
                   (new_amount, new_date, eid, uid))
    diff = new_amount - old_amount
    cursor.execute("UPDATE categories SET total_expense = total_expense + %s WHERE category_id=%s AND user_id=%s",
                   (diff, cid, uid))
    db.commit()
    return redirect('/manage_expenses')

# delete expense
@app.route('/delete_expense/<int:eid>')
def delete_expense(eid):
    if 'user_id' not in session:
        return redirect('/login')
    uid = session['user_id']
    cursor.execute("SELECT category_id, amount FROM expenses WHERE expense_id=%s AND user_id=%s", (eid, uid))
    row = cursor.fetchone()
    if not row:
        return redirect('/manage_expenses')
    cid = row['category_id']
    amount = float(row['amount'])
    cursor.execute("DELETE FROM expenses WHERE expense_id=%s AND user_id=%s", (eid, uid))
    cursor.execute("UPDATE categories SET total_expense = total_expense - %s WHERE category_id=%s AND user_id=%s",
                   (amount, cid, uid))
    db.commit()
    return redirect('/manage_expenses')

# home (dashboard)
@app.route('/home', methods=['GET','POST'])
def home():
    if 'user_id' not in session:
        return redirect('/login')
    uid = session['user_id']

    # handle POST actions on home (set budget or add expense if you prefer keeping single-page forms)
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'set_budget':
            cid = request.form['category_id']
            budget = float(request.form['budget'])
            cursor.execute("UPDATE categories SET budget=%s WHERE category_id=%s AND user_id=%s",
                           (budget, cid, uid))
            db.commit()
            return redirect('/home')
        if action == 'add_expense':
            cid = request.form['category_id']
            amount = float(request.form['amount'])
            date = request.form.get('date') or datetime.today().strftime('%Y-%m-%d')
            cursor.execute("INSERT INTO expenses (user_id, category_id, amount, date) VALUES (%s,%s,%s,%s)",
                           (uid, cid, amount, date))
            cursor.execute("UPDATE categories SET total_expense = total_expense + %s WHERE category_id=%s AND user_id=%s",
                           (amount, cid, uid))
            db.commit()
            return redirect('/home')

    # fetch categories & totals
    cursor.execute("SELECT * FROM categories WHERE user_id=%s", (uid,))
    categories = cursor.fetchall()
    category_labels = [c['category_name'] for c in categories]
    category_totals = [float(c['total_expense']) for c in categories]

    # month options for bar chart
    cursor.execute("SELECT DISTINCT YEAR(date) AS yr, MONTH(date) AS mn FROM expenses WHERE user_id=%s ORDER BY yr DESC, mn DESC", (uid,))
    months = cursor.fetchall()
    if months:
        month_options = [f"{m['yr']}-{m['mn']:02d}" for m in months]
    else:
        today = datetime.today()
        month_options = [f"{today.year}-{today.month:02d}"]
    selected_month = request.args.get('month') or month_options[0]
    y, m = map(int, selected_month.split('-'))

    # bar chart data for selected month
    cursor.execute("""
        SELECT c.category_name, COALESCE(SUM(e.amount),0) AS total
        FROM categories c
        LEFT JOIN expenses e
            ON c.category_id = e.category_id
            AND YEAR(e.date)=%s
            AND MONTH(e.date)=%s
            AND e.user_id=%s
        WHERE c.user_id=%s
        GROUP BY c.category_id
    """, (y, m, uid, uid))
    rows = cursor.fetchall()
    bar_labels = [r['category_name'] for r in rows]
    bar_values = [float(r['total']) for r in rows]

    # expense list per category for potential small displays
    expenses_dict = {}
    for c in categories:
        cursor.execute("SELECT expense_id, amount, date, category_id FROM expenses WHERE user_id=%s AND category_id=%s ORDER BY date DESC", (uid, c['category_id']))
        expenses_dict[c['category_id']] = cursor.fetchall()

    # totals
    cursor.execute("SELECT total_income FROM users WHERE user_id=%s", (uid,))
    income_row = cursor.fetchone()
    total_income = float(income_row['total_income']) if income_row else 0
    cursor.execute("SELECT COALESCE(SUM(amount),0) AS total FROM expenses WHERE user_id=%s", (uid,))
    tr = cursor.fetchone()
    total_expense = float(tr['total']) if tr else 0

    return render_template('home.html',
                           username=session['username'],
                           total_income=total_income,
                           total_expense=total_expense,
                           categories=categories,
                           expenses=expenses_dict,
                           category_labels=category_labels,
                           category_totals=category_totals,
                           month_options=month_options,
                           selected_month=selected_month,
                           bar_labels=bar_labels,
                           bar_values=bar_values)

if __name__ == '__main__':
    app.run(debug=True)
