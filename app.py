from flask import Flask, render_template, request, redirect, url_for, jsonify, json, session
import sqlite3
from datetime import datetime
import os

import stripe

import requests
from requests.auth import HTTPBasicAuth


endpoint_secret = os.getenv('STRIPE_WEBHOOK_SECRET')




# PayPal API credentials (Sandbox for now)
PAYPAL_CLIENT_ID = os.getenv('PAYPAL_CLIENT_ID')
PAYPAL_SECRET = os.getenv('PAYPAL_SECRET')
PAYPAL_API_BASE = 'https://api-m.paypal.com'
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")




app = Flask(__name__)
DATABASE_PATH = os.getenv("DATABASE_PATH", "/data/database.db")
app.secret_key = os.getenv("FLASK_SECRET")

@app._got_first_request
def initialize():
    init_db()


def init_db():
    database_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database.db')
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    print(f"Initializing DB at: {DATABASE_PATH}")
    c.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY,
            username TEXT,
            amount REAL,
            city TEXT,
            timestamp TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS paypal_orders (
            order_id TEXT PRIMARY KEY,
            custom_id TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS pending_cities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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


sweden_cities = [
    "Stockholm", "Gothenburg", "Malmö", "Uppsala", "Linköping", "Örebro", 
    "Västerås", "Helsingborg", "Norrköping", "Jönköping"
]

def get_approved_cities():
    predefined = [
        "Stockholm", "Gothenburg", "Malmö", "Uppsala", "Linköping", "Örebro", 
        "Västerås", "Helsingborg", "Norrköping", "Jönköping"
    ]

    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT name FROM approved_cities")
    user_approved = [row[0] for row in c.fetchall()]
    conn.close()

    combined = sorted(set(predefined + user_approved), key=str.lower)

    if "Other" in combined:
        combined.remove("Other")
        combined.append("Other")

    return combined

def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

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
        if password == os.getenv("ADMIN_PASSWORD"):  # eller hårdkoda t.ex. 'superhemligt'
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
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()

    # Pagination parameters
    items_per_page = 10  # Configurable number of entries per page
    player_page = int(request.args.get('player_page', 1))  # Default to page 1
    city_page = int(request.args.get('city_page', 1))      # Default to page 1
    player_offset = (player_page - 1) * items_per_page
    city_offset = (city_page - 1) * items_per_page

    # Individual leaderboard with pagination

    c.execute("""
        SELECT username, (
            SELECT city 
            FROM payments p2 
            WHERE p2.username = p1.username 
            ORDER BY p2.timestamp DESC 
            LIMIT 1
        ), SUM(amount) 
        FROM payments p1 
        GROUP BY username 
        ORDER BY SUM(amount) DESC 
        LIMIT ? OFFSET ?
    """, (items_per_page, player_offset))

    # Add emoji based on total amount
    leaderboard = [
        (
            i + 1 + player_offset,
            "👑 " + row[0] if row[2] >= 1000 else
            "💎 " + row[0] if row[2] >= 500 else
            "💰 " + row[0] if row[2] >= 100 else
            row[0],
            row[1],
            row[2]
        )
        for i, row in enumerate(c.fetchall())
    ]

    available_images = [
    'Stockholm', 'Göteborg', 'Malmö', 'Uppsala', 'Linköping', 'Örebro',
    'Västerås', 'Helsingborg', 'Norrköping', 'Jönköping'
    ]


    # Total number of players for pagination
    c.execute("SELECT COUNT(DISTINCT username) FROM payments")
    total_players = c.fetchone()[0]
    total_player_pages = (total_players + items_per_page - 1) // items_per_page

    # City leaderboard with pagination
    c.execute("""
        SELECT city, COUNT(*) as donation_count, SUM(amount) 
        FROM payments 
        WHERE city IS NOT NULL 
        GROUP BY city 
        ORDER BY SUM(amount) DESC 
        LIMIT ? OFFSET ?
    """, (items_per_page, city_offset))
    city_leaderboard = [(i + 1 + city_offset, row[0], row[1], row[2]) for i, row in enumerate(c.fetchall())]

    # Total number of cities for pagination
    c.execute("SELECT COUNT(DISTINCT city) FROM payments WHERE city IS NOT NULL")
    total_cities = c.fetchone()[0]
    total_city_pages = (total_cities + items_per_page - 1) // items_per_page

    conn.close()

    # Build a set of available city image filenames (without extension)
    image_dir = os.path.join(app.static_folder, 'images')
    available_images = {
        os.path.splitext(f)[0].lower()
        for f in os.listdir(image_dir)
        if f.endswith('.jpg')
    }
    image_folder = os.path.join(app.static_folder, 'images')
    available_images = [
    os.path.splitext(filename)[0].lower()
    for filename in os.listdir(image_folder)
    if filename.endswith('.jpg')
    ]   


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
    error_message = None
    if error == 'amount_too_small':
        error_message = "The amount must be at least 1 SEK"

    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()

    c.execute("SELECT username, amount FROM payments ORDER BY amount DESC")
    leaderboard = c.fetchall()

    c.execute("""
        SELECT city, COUNT(*) as donation_count, SUM(amount) 
        FROM payments 
        WHERE city IS NOT NULL 
        GROUP BY city 
        ORDER BY SUM(amount) DESC
    """)
    city_leaderboard = [(i + 1, row[0], row[1], row[2]) for i, row in enumerate(c.fetchall())]

    rank = None
    for index, entry in enumerate(leaderboard):
        if entry[0] == username:
            rank = index + 1
            break

    conn.close()
    return render_template('payment_success.html', username=username, amount=amount, 
                           city=city, error_message=error_message, rank=rank, city_leaderboard=city_leaderboard)

@app.route('/pay', methods=['POST'])
def pay():
    username = request.form['username']
    amount = float(request.form['amount'])
    city = request.form.get('city')
    custom_city = request.form.get('custom_city')

    if city.lower() in ['other', 'annan']:

        if custom_city and custom_city.strip():
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute(
                "INSERT INTO pending_cities (name, submitted_by, timestamp) VALUES (?, ?, ?)",
                (custom_city.strip(), username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        conn.close()

    city = 'Other'  # så leaderboarden inte får custom direkt


    if city == 'None' or not city:
        city = None

    return redirect(url_for('payment_page', username=username, amount=amount, city=city))


@app.route('/payment')
def payment_page():
    username = request.args.get('username')
    amount = request.args.get('amount')
    city = request.args.get('city')
    return render_template('payment.html', username=username, amount=amount, city=city)

@app.route('/process-payment', methods=['POST'])
def process_payment():
    username = request.form.get('username')
    amount = request.form.get('amount')
    city = request.form.get('city')
    payment_method = request.form.get('payment_method')

    if not username or not amount:
        return redirect(url_for('payment_page', error="Missing required fields"))

    try:
        amount = float(amount)
        if amount < 1:
            return redirect(url_for('payment_success', username=username, amount=amount, city=city, error='amount_too_small'))
    except ValueError:
        return redirect(url_for('payment_page', error="Invalid amount"))

    # Process based on payment method
    if payment_method == "Swish":
        phone = request.form.get('phone')
        if not phone:
            return redirect(url_for('payment_page', error="Phone number is required for Swish"))

    elif payment_method == "Credit Card":
        card_number = request.form.get('card-number')
        expiry = request.form.get('expiry')
        cvc = request.form.get('cvc')
        if not (card_number and expiry and cvc):
            return redirect(url_for('payment_page', error="All credit card fields are required"))

    # Insert into database
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO payments (username, amount, city, timestamp) VALUES (?, ?, ?, ?)",
              (username, amount, city, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

    return redirect(url_for('payment_success', username=username, amount=amount, city=city))

@app.route('/paypal/webhook', methods=['POST'])
def paypal_webhook():
    print("🚨 Webhook träffad?")
    print(f"Headers: {dict(request.headers)}")
    print(f"Body: {request.get_data(as_text=True)}")
    try:
        data = request.get_json()
        print("📥 Received webhook data:")
        print(json.dumps(data, indent=2))

        event_type = data.get('event_type')

        # Automatically handle CHECKOUT.ORDER.APPROVED → capture it
        if event_type == "CHECKOUT.ORDER.APPROVED":
            order_id = data["resource"]["id"]
            print(f"⚡ Capturing order: {order_id}")

            # Step 1: Get new access token
            auth_response = requests.post(
                f"{PAYPAL_API_BASE}/v1/oauth2/token",
                headers={'Accept': 'application/json'},
                data={'grant_type': 'client_credentials'},
                auth=HTTPBasicAuth(PAYPAL_CLIENT_ID, PAYPAL_SECRET)
            )
            access_token = auth_response.json()['access_token']

            # Step 2: Capture the order
            capture_response = requests.post(
                f"{PAYPAL_API_BASE}/v2/checkout/orders/{order_id}/capture",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}"
                }
            )

            print("💳 Capture response:")
            print(json.dumps(capture_response.json(), indent=2))

            return jsonify({"status": "captured"}), 200

        # This is the one that inserts into DB
        if event_type == 'PAYMENT.CAPTURE.COMPLETED':
            resource = data.get('resource', {})
            print("🔥 Webhook resource payload:")
            print(json.dumps(resource, indent=2))
            amount = 0
            try:
                amount = float(resource.get('amount', {}).get('value', 0))
            except:
                try:
                    captures = resource.get('purchase_units', [{}])[0].get('payments', {}).get('captures', [])
                    if captures:
                        amount = float(captures[0].get('amount', {}).get('value', 0))
                except Exception as e:
                    print(f"⚠️ Failed to parse amount: {e}")

            print(f"📦 Extracted amount: {amount}")
            # Get order ID from the webhook payload
            order_id = resource.get('supplementary_data', {}).get('related_ids', {}).get('order_id')
            if not order_id:
                print("❌ Missing order_id in webhook capture")
                return jsonify({'error': 'Missing order_id'}), 400

            # Look up the custom_id from the local database
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute("SELECT custom_id FROM paypal_orders WHERE order_id = ?", (order_id,))
            result = c.fetchone()
            conn.close()

            if not result:
                print(f"❌ No custom_id mapping found for order_id: {order_id}")
                return jsonify({'error': 'Order not found'}), 404

            custom_id = result[0]
            username, city = custom_id.split('|')
            if city not in sweden_cities:
                print(f"📝 '{city}' verkar vara en ny stad. Sparar till pending_cities...")
                conn = sqlite3.connect(DATABASE_PATH)
                c = conn.cursor()
                c.execute(
                    "INSERT INTO pending_cities (name, submitted_by, timestamp) VALUES (?, ?, ?)",
                    (city, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                )
                conn.commit()
                conn.close()
            if amount < 1:
                return jsonify({'error': 'Invalid amount'}), 400

            # Insert payment
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute(
                "INSERT INTO payments (username, amount, city, timestamp) VALUES (?, ?, ?, ?)",
                (username, amount, city if city != 'None' else None, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            conn.commit()
            conn.close()

            print(f"✅ Parsed payment: {username}, {city}, {amount} SEK")
            print("✅ Payment inserted into DB.")
            return jsonify({'status': 'success'}), 200



        # Ignore all other event types
        print("ℹ️ Ignored event type:", event_type)
        return jsonify({'status': 'ignored'}), 200

    except Exception as e:
        print("❌ Webhook processing failed:", str(e))
        return jsonify({'error': 'Webhook error'}), 500




@app.route('/create-paypal-order', methods=['POST'])
def create_paypal_order():
    data = request.get_json()
    username = data.get('username')
    amount = float(data.get('amount'))
    city = data.get('city') or 'None'

    # 🔥 Om någon angett manuell stad, spara i pending_cities
    if '|' in city:  # quick check if it's in format "Username|City"
        city_parts = city.split('|')
        if len(city_parts) == 2:
            raw_city = city_parts[1]
            if raw_city.lower() not in [c.lower() for c in sweden_cities] and raw_city.lower() != 'other':
                conn = sqlite3.connect(DATABASE_PATH)
                c = conn.cursor()
                c.execute(
                    "INSERT INTO pending_cities (name, submitted_by, timestamp) VALUES (?, ?, ?)",
                    (raw_city, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                )
                conn.commit()
                conn.close()


    # Step 1: Get Access Token
    auth_response = requests.post(
        f'{PAYPAL_API_BASE}/v1/oauth2/token',
        headers={'Accept': 'application/json'},
        data={'grant_type': 'client_credentials'},
        auth=HTTPBasicAuth(PAYPAL_CLIENT_ID, PAYPAL_SECRET)
    )
    access_token = auth_response.json()['access_token']

    # Step 2: Create order
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

    # Save to DB
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO paypal_orders (order_id, custom_id) VALUES (?, ?)", (order_id, custom_id))
    conn.commit()
    conn.close()

    approval_url = next(link['href'] for link in order['links'] if link['rel'] == 'approve')
    return {'approval_url': approval_url}

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('admin'):
        return redirect(url_for('login'))
    
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()

    if request.method == 'POST':
        approved_ids = request.form.getlist('approve')
        for city_id in approved_ids:
            c.execute("SELECT name, submitted_by FROM pending_cities WHERE id = ?", (city_id,))
            result = c.fetchone()
            if result:
                city_name, submitted_by = result
                c.execute("INSERT OR IGNORE INTO approved_cities (name) VALUES (?)", (city_name,))
                c.execute("""
                    UPDATE payments 
                    SET city = ? 
                    WHERE city = 'Other' AND username = ?
                """, (city_name, submitted_by))
                c.execute("DELETE FROM pending_cities WHERE id = ?", (city_id,))
        conn.commit()
    
    # 💡 Oavsett GET eller POST – hämta pending cities och rendera admin-sidan
    c.execute("SELECT id, name, submitted_by, timestamp FROM pending_cities")
    pending = c.fetchall()
    conn.close()
    return render_template('admin.html', pending=pending)

@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    username = request.form.get('username')
    amount = int(float(request.form.get('amount')) * 100)
    city = request.form.get('city')
    custom_city = request.form.get('custom_city', '').strip()

    # Om användaren valde "Other" och skrev något
    if city == 'Other' and custom_city:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO pending_cities (name, submitted_by, timestamp) VALUES (?, ?, ?)",
            (custom_city, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        conn.close()
        city = 'Other'  # Fortfarande för leaderboard

    # Ersätt med manuellt inskriven stad om vald
    if city.lower() in ['annan', 'other'] and custom_city.strip():
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO pending_cities (name, submitted_by, timestamp) VALUES (?, ?, ?)",
            (custom_city.strip(), username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        conn.close()
        city = 'Other'


    session = stripe.checkout.Session.create(
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
        },
        success_url = url_for('success', username=username, amount=amount / 100, city=city, _external=True),
        cancel_url=url_for('index', _external=True),
    )
    return redirect(session.url, code=303)

@app.route('/success')
def success():
    username = request.args.get('username')
    amount = request.args.get('amount')
    city = request.args.get('city')

    # Hämta rank från databasen
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT username, SUM(amount) FROM payments GROUP BY username ORDER BY SUM(amount) DESC")
    leaderboard = c.fetchall()

    rank = None
    for index, entry in enumerate(leaderboard):
        if entry[0] == username:
            rank = index + 1
            break

    conn.close()

    return render_template('success.html',
                           username=username,
                           amount=amount,
                           city=city,
                           rank=rank)


@app.route('/stripe/webhook', methods=['POST'])
def stripe_webhook():
    import json
    payload = request.data
    sig_header = request.headers.get('stripe-signature')
    endpoint_secret = os.getenv('STRIPE_WEBHOOK_SECRET')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except Exception as e:
        return str(e), 400

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        metadata = session.get('metadata', {})
        username = metadata.get('username')
        amount = float(metadata.get('amount'))
        city = metadata.get('city')

        conn = get_db_connection()
        cursor = conn.cursor()

        if event['type'] == 'checkout.session.completed':
            print("✅ Stripe webhook: Session completed")
            print(json.dumps(event, indent=2))

            session = event['data']['object']
            metadata = session.get('metadata', {})
            print(f"📦 Metadata: {metadata}")
            
        cursor.execute("""
            INSERT INTO payments (username, amount, city, timestamp)
            VALUES (?, ?, ?, ?)
        """, (username, amount, city, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))


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

    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO payments (username, amount, city, timestamp)
        VALUES (?, ?, ?, ?)
    """, (username, amount, city, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

    return redirect(url_for('admin'))

if __name__ == "__main__":
    init_db()
    app.run(debug=True)