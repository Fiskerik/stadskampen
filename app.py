from flask import Flask, render_template, request, redirect, url_for, jsonify, json, session
from datetime import datetime
import os
import stripe
import requests
from requests.auth import HTTPBasicAuth
import psycopg2 # type: ignore
import psycopg2.extras # type: ignore

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET")
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
endpoint_secret = os.getenv('STRIPE_WEBHOOK_SECRET')

PAYPAL_CLIENT_ID = os.getenv('PAYPAL_CLIENT_ID')
PAYPAL_SECRET = os.getenv('PAYPAL_SECRET')
PAYPAL_API_BASE = 'https://api-m.paypal.com'
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            username TEXT,
            amount REAL,
            city TEXT,
            timestamp TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS pending_cities (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            submitted_by TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS approved_cities (
            name TEXT PRIMARY KEY
        )
    ''')
    conn.commit()
    conn.close()

init_db()

sweden_cities = [
    "Stockholm", "Göteborg", "Malmö", "Uppsala", "Västerås", "Örebro",
    "Linköping", "Helsingborg", "Jönköping", "Norrköping", "Lund",
    "Umeå", "Gävle", "Borås", "Eskilstuna", "Södertälje", "Karlstad",
    "Halmstad", "Växjö", "Sundsvall", "Luleå", "Trollhättan", "Östersund",
    "Borlänge", "Kristianstad", "Kalmar", "Skövde", "Karlskrona", "Falun"
]

def get_approved_cities():
    predefined = [
        "Stockholm", "Göteborg", "Malmö", "Uppsala", "Västerås", "Örebro",
        "Linköping", "Helsingborg", "Jönköping", "Norrköping", "Lund",
        "Umeå", "Gävle", "Borås", "Eskilstuna", "Södertälje", "Karlstad",
        "Halmstad", "Växjö", "Sundsvall", "Luleå", "Trollhättan", "Östersund",
        "Borlänge", "Kristianstad", "Kalmar", "Skövde", "Karlskrona", "Falun"
    ]
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT name FROM approved_cities")
    user_approved = [row['name'] for row in c.fetchall()]
    conn.close()
    combined = sorted(set(predefined + user_approved), key=str.lower)
    if "Övrig" in combined:
        combined.remove("Övrig")
        combined.append("Övrig")
    return combined

@app.before_request
def restrict_admin():
    if request.endpoint == 'admin' and not session.get('admin'):
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    session.permanent = False
    session['admin'] = True
    error = None
    if request.method == 'POST':
        password = request.form.get('password')
        if password == os.getenv("ADMIN_PASSWORD"):
            session['admin'] = True
            return redirect(url_for('admin'))
        else:
            error = "Fel lösenord"
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('index'))
@app.route('/')
def index():
    conn = get_db_connection()
    c = conn.cursor()

    items_per_page = 10
    player_page = int(request.args.get('player_page', 1))
    city_page = int(request.args.get('city_page', 1))
    player_offset = (player_page - 1) * items_per_page
    city_offset = (city_page - 1) * items_per_page

    c.execute("""
        SELECT p1.username,
            MAX(p1.city) AS latest_city,
            MAX(p1.message) FILTER (WHERE p1.timestamp = sub.latest_timestamp) AS latest_message,
            SUM(p1.amount) AS total
        FROM payments p1
        JOIN (
            SELECT username, MAX(timestamp) AS latest_timestamp
            FROM payments
            GROUP BY username
        ) sub ON sub.username = p1.username
        GROUP BY p1.username
        ORDER BY total DESC
        LIMIT %s OFFSET %s
    """, (items_per_page, player_offset))


    leaderboard = [
        (
            i + 1 + player_offset,
            "👑 " + row['username'] if row['total'] >= 1000 else
            "💎 " + row['username'] if row['total'] >= 500 else
            "💰 " + row['username'] if row['total'] >= 100 else
            "💵 " + row['username'] if row['total'] >= 50 else
            row['username'],
            row['latest_city'],
            row['total'],
            row['latest_message']  # 🆕 Hälsning
        )
        for i, row in enumerate(c.fetchall())
    ]


    c.execute("SELECT COUNT(DISTINCT username) FROM payments")
    total_players = c.fetchone()['count']
    total_player_pages = (total_players + items_per_page - 1) // items_per_page

    c.execute("""
        SELECT city, COUNT(*) as donation_count, SUM(amount) as total 
        FROM payments 
        WHERE city IS NOT NULL 
        GROUP BY city 
        ORDER BY total DESC 
        LIMIT %s OFFSET %s
    """, (items_per_page, city_offset))
    city_leaderboard = [
        (i + 1 + city_offset, row['city'], row['donation_count'], row['total'])
        for i, row in enumerate(c.fetchall())
    ]

    c.execute("SELECT COUNT(DISTINCT city) FROM payments WHERE city IS NOT NULL")
    total_cities = c.fetchone()['count']
    total_city_pages = (total_cities + items_per_page - 1) // items_per_page

    conn.close()

    image_dir = os.path.join(app.static_folder, 'images')
    available_images = {
        os.path.splitext(f)[0].lower()
        for f in os.listdir(image_dir)
        if f.endswith('.jpg')
    }

    return render_template('index.html',
        leaderboard=leaderboard,
        city_leaderboard=city_leaderboard,
        cities=sweden_cities,
        player_page=player_page,
        city_page=city_page,
        total_player_pages=total_player_pages,
        total_city_pages=total_city_pages,
        available_images=available_images,
    )

@app.route('/faq')
def faq():
    return render_template('faq.html')

@app.route('/privacy_policy')
def privacy_policy():
    return render_template('privacy_policy.html')

@app.route('/disclaimer')
def disclaimer():
    return render_template('disclaimer.html')

@app.route('/payment-success')
def payment_success():
    username = request.args.get('username')
    amount = request.args.get('amount')
    city = request.args.get('city')

    error = request.args.get('error')
    error_message = "The amount must be at least 1 SEK" if error == 'amount_too_small' else None

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT username, amount FROM payments ORDER BY amount DESC")
    leaderboard = c.fetchall()

    c.execute("""
        SELECT city, COUNT(*) as donation_count, SUM(amount) as total
        FROM payments
        WHERE city IS NOT NULL
        GROUP BY city
        ORDER BY total DESC
    """)
    city_leaderboard = [
        (i + 1, row['city'], row['donation_count'], row['total'])
        for i, row in enumerate(c.fetchall())
    ]

    rank = next((index + 1 for index, entry in enumerate(leaderboard) if entry['username'] == username), None)
    conn.close()

    return render_template('payment_success.html', username=username, amount=amount, 
                           city=city, error_message=error_message, rank=rank, city_leaderboard=city_leaderboard)

@app.route('/pay', methods=['POST'])
def pay():
    username = request.form['username']
    amount = request.form['amount']
    city = request.form.get('city')
    custom_city = request.form.get('custom_city')
    message = request.form.get('message')

    if city and city.lower() in ['övrig', 'annan'] and custom_city and custom_city.strip():
        # Save pending city immediately (this part is okay)
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "INSERT INTO pending_cities (name, submitted_by, timestamp) VALUES (%s, %s, %s)",
            (custom_city.strip(), username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        conn.close()
        city = 'Övrig'

    if city == 'None' or not city:
        city = None

    # Pass info to the payment options page (or pass via session instead)
    return redirect(url_for('payment_page', username=username, amount=amount, city=city, message=message))



@app.route('/payment')
def payment_page():
    username = request.args.get('username')
    amount = request.args.get('amount')
    city = request.args.get('city')
    message = request.args.get('message') 
    return render_template('payment.html', username=username, amount=amount, city=city)

@app.route('/process-payment', methods=['POST'])
def process_payment():
    username = request.form.get('username')
    amount = request.form.get('amount')
    city = request.form.get('city')
    message = request.form.get('message')  # 🆕 Nytt fält
    payment_method = request.form.get('payment_method')

    if not username or not amount:
        return redirect(url_for('payment_page', error="Missing required fields"))

    try:
        amount = float(amount)
        if amount < 1:
            return redirect(url_for('payment_success', username=username, amount=amount, city=city, error='amount_too_small'))
    except ValueError:
        return redirect(url_for('payment_page', error="Invalid amount"))

    if payment_method == "Swish" and not request.form.get('phone'):
        return redirect(url_for('payment_page', error="Phone number is required for Swish"))

    if payment_method == "Credit Card":
        if not all([request.form.get('card-number'), request.form.get('expiry'), request.form.get('cvc')]):
            return redirect(url_for('payment_page', error="All credit card fields are required"))

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO payments (username, amount, city, timestamp, message)
        VALUES (%s, %s, %s, %s, %s)
    """, (username, amount, city, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), message))
    conn.commit()
    conn.close()

    return redirect(url_for('payment_success', username=username, amount=amount, city=city))

@app.route('/paypal/webhook', methods=['POST'])
def paypal_webhook():
    try:
        data = request.get_json()
        event_type = data.get('event_type')

        if event_type == "CHECKOUT.ORDER.APPROVED":
            order_id = data["resource"]["id"]

            auth_response = requests.post(
                f"{PAYPAL_API_BASE}/v1/oauth2/token",
                headers={'Accept': 'application/json'},
                data={'grant_type': 'client_credentials'},
                auth=HTTPBasicAuth(PAYPAL_CLIENT_ID, PAYPAL_SECRET)
            )
            access_token = auth_response.json()['access_token']

            capture_response = requests.post(
                f"{PAYPAL_API_BASE}/v2/checkout/orders/{order_id}/capture",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}"
                }
            )

            return jsonify({"status": "captured"}), 200

        if event_type == 'PAYMENT.CAPTURE.COMPLETED':
            resource = data.get('resource', {})
            amount = 0
            try:
                amount = float(resource.get('amount', {}).get('value', 0))
            except:
                try:
                    captures = resource.get('purchase_units', [{}])[0].get('payments', {}).get('captures', [])
                    if captures:
                        amount = float(captures[0].get('amount', {}).get('value', 0))
                except:
                    pass

            order_id = resource.get('supplementary_data', {}).get('related_ids', {}).get('order_id')
            if not order_id:
                return jsonify({'error': 'Missing order_id'}), 400

            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT custom_id FROM paypal_orders WHERE order_id = %s", (order_id,))
            result = c.fetchone()
            if not result:
                conn.close()
                return jsonify({'error': 'Order not found'}), 404

            custom_id = result['custom_id']
            username, city = custom_id.split('|')
            if city not in sweden_cities:
                c.execute(
                    "INSERT INTO pending_cities (name, submitted_by, timestamp) VALUES (%s, %s, %s)",
                    (city, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                )

            if amount >= 1:
                # Get message from paypal_orders
                c.execute("SELECT message FROM paypal_orders WHERE order_id = %s", (order_id,))
                msg_row = c.fetchone()
                message = msg_row['message'] if msg_row else None

                c.execute(
                    "INSERT INTO payments (username, amount, city, timestamp, message) VALUES (%s, %s, %s, %s, %s)",
                    (username, amount, city if city != 'None' else None, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), message)
                )


            conn.commit()
            conn.close()
            return jsonify({'status': 'success'}), 200

        return jsonify({'status': 'ignored'}), 200

    except Exception as e:
        return jsonify({'error': 'Webhook error'}), 500

@app.route('/create-paypal-order', methods=['POST'])
def create_paypal_order():
    data = request.get_json()
    username = data.get('username')
    amount = float(data.get('amount'))
    city = data.get('city') or 'None'

    if '|' in city:
        parts = city.split('|')
        if len(parts) == 2:
            raw_city = parts[1]
            if raw_city.lower() not in [c.lower() for c in sweden_cities] and raw_city.lower() != 'övrig':
                conn = get_db_connection()
                c = conn.cursor()
                c.execute(
                    "INSERT INTO pending_cities (name, submitted_by, timestamp) VALUES (%s, %s, %s)",
                    (raw_city, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                )
                conn.commit()
                conn.close()

    auth_response = requests.post(
        f'{PAYPAL_API_BASE}/v1/oauth2/token',
        headers={'Accept': 'application/json'},
        data={'grant_type': 'client_credentials'},
        auth=HTTPBasicAuth(PAYPAL_CLIENT_ID, PAYPAL_SECRET)
    )
    access_token = auth_response.json()['access_token']

    order_response = requests.post(
        f'{PAYPAL_API_BASE}/v2/checkout/orders',
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}',
        },
        json={
            "intent": "CAPTURE",
            "purchase_units": [{
                "amount": {
                    "currency_code": "SEK",
                    "value": f"{amount:.2f}"
                },
                "custom_id": f"{username}|{city}"
            }],
            "application_context": {
                "return_url": url_for('payment_success', username=username, amount=amount, city=city, _external=True),
                "cancel_url": url_for('payment_page', username=username, amount=amount, city=city, _external=True)
            }
        }
    )

    if order_response.status_code != 201:
        return {'error': 'Failed to create PayPal order'}, 500

    order = order_response.json()
    order_id = order['id']
    custom_id = f"{username}|{city}"

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
    INSERT INTO paypal_orders (order_id, custom_id, message)
    VALUES (%s, %s, %s)
    ON CONFLICT (order_id) DO UPDATE
    SET custom_id = EXCLUDED.custom_id,
        message = EXCLUDED.message
    """, (order_id, custom_id, data.get('message')))

    conn.commit()
    conn.close()

    approval_url = next(link['href'] for link in order['links'] if link['rel'] == 'approve')
    return {'approval_url': approval_url}

@app.route('/admin')
def admin():
    if not session.get('admin'):
        return redirect(url_for('login'))

    page = int(request.args.get('page', 1))
    per_page = 10
    offset = (page - 1) * per_page

    conn = get_db_connection()
    c = conn.cursor()

    # Pending cities
    c.execute("SELECT id, name, submitted_by, timestamp FROM pending_cities")
    pending = c.fetchall()

    # Payments
    c.execute("SELECT * FROM payments ORDER BY timestamp DESC LIMIT %s OFFSET %s", (per_page, offset))
    payments = c.fetchall()
    c.execute("SELECT * FROM payments ORDER BY timestamp DESC LIMIT 10")
    payments = c.fetchall()


    c.execute("SELECT COUNT(*) FROM payments")
    total = c.fetchone()['count']
    total_pages = (total + per_page - 1) // per_page

    conn.close()
    return render_template('admin.html', pending=pending, payments=payments, page=page, total_pages=total_pages)




@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    username = request.form.get('username')
    amount = int(float(request.form.get('amount')) * 100)
    city = request.form.get('city')
    custom_city = request.form.get('custom_city', '').strip()
    message = request.form.get('message')

    if city.lower() in ['övrig', 'annan'] and custom_city:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "INSERT INTO pending_cities (name, submitted_by, timestamp) VALUES (%s, %s, %s)",
            (custom_city.strip(), username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        conn.close()
        city = 'Övrig'

    session_obj = stripe.checkout.Session.create(
        payment_method_types=['card'],
        mode='payment',
        line_items=[{
            'price_data': {
                'currency': 'sek',
                'product_data': {
                    'name': f'Donation från {username}',
                },
                'unit_amount': amount,
            },
            'quantity': 1,
        }],
        metadata={
            'username': username,
            'amount': amount / 100,
            'city': city,
            'message': message  # ✅ add this
        },
        success_url=url_for('success', username=username, amount=amount / 100, city=city, _external=True),
        cancel_url=url_for('index', _external=True),
    )
    return redirect(session_obj.url, code=303)

@app.route('/success')
def success():
    username = request.args.get('username')
    amount = request.args.get('amount')
    city = request.args.get('city')

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT username, SUM(amount) as total FROM payments GROUP BY username ORDER BY total DESC")
    leaderboard = c.fetchall()

    rank = next((index + 1 for index, entry in enumerate(leaderboard) if entry['username'] == username), None)
    conn.close()

    return render_template('success.html', username=username, amount=amount, city=city, rank=rank)

@app.route('/stripe/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except Exception as e:
        return str(e), 400

    if event['type'] == 'payment_intent.succeeded':
        intent = event['data']['object']
        metadata = intent.get('metadata', {})
        username = metadata.get('username')
        amount = float(metadata.get('amount'))
        city = metadata.get('city')
        message = metadata.get('message')  # Optional

        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "INSERT INTO payments (username, amount, city, timestamp, message) VALUES (%s, %s, %s, %s, %s)",
            (username, amount, city, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), message)
        )
        conn.commit()
        conn.close()

    return '', 200


@app.route('/admin/manual-add', methods=['POST'])
def manual_add():
    if not session.get('admin'):
        return redirect(url_for('login'))

    username = request.form.get('username')
    amount = request.form.get('amount')
    city = request.form.get('city')

    try:
        amount = float(amount)
    except ValueError:
        return "Ogiltigt belopp"

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO payments (username, amount, city, timestamp)
        VALUES (%s, %s, %s, %s)
    """, (username, amount, city, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

    return redirect(url_for('admin'))

@app.route('/admin/edit-payments', methods=['GET'])
def admin_edit_payments():
    if not session.get('admin'):
        return redirect(url_for('login'))

    page = int(request.args.get('page', 1))
    per_page = 10
    offset = (page - 1) * per_page

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM payments
        ORDER BY timestamp DESC
        LIMIT %s OFFSET %s
    """, (per_page, offset))
    payments = c.fetchall()

    c.execute("SELECT COUNT(*) FROM payments")
    total = c.fetchone()['count']
    total_pages = (total + per_page - 1) // per_page
    conn.close()

    return render_template("admin_edit.html", payments=payments, page=page, total_pages=total_pages)

@app.route('/admin/update-payment', methods=['POST'])
def update_payment():
    if not session.get('admin'):
        return redirect(url_for('login'))

    payment_id = request.form['id']
    username = request.form['username']
    amount = float(request.form['amount'])
    city = request.form['city']
    message = request.form['message']

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE payments 
        SET username = %s, amount = %s, city = %s, message = %s 
        WHERE id = %s
    """, (username, amount, city, message, payment_id))
    conn.commit()
    conn.close()


    return redirect(url_for('admin'))

@app.route('/admin/delete-payment', methods=['POST'])
def delete_payment():
    data = request.get_json()
    payment_id = data.get('id')

    if not payment_id:
        return jsonify({'error': 'Missing ID'}), 400

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM payments WHERE id = %s", (payment_id,))
    conn.commit()
    conn.close()

    return jsonify({'status': 'deleted'})

@app.route('/admin/add-paypal-message')
def add_paypal_message_column():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('ALTER TABLE paypal_orders ADD COLUMN message TEXT')
    conn.commit()
    conn.close()
    return 'Column added successfully.'




if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0")