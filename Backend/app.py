import base64
import requests
import jwt as pyjwt
from jwt import PyJWKClient
from flask import request, make_response, jsonify
from config import app, api, db, os, bcrypt, CLERK_JWKS_URL
from models import Customer, Driver, Order, ScheduledMove, Payment, OTP, AppSettings, Rating, Vehicle, Ride
from flask_restful import Resource
from utils.distance import haversine
from datetime import datetime
from decimal import Decimal
from sqlalchemy.exc import IntegrityError
import uuid
import pyotp
import smtplib
from flask_jwt_extended import create_access_token, create_refresh_token
from flask_jwt_extended import get_jwt_identity, current_user
from flask_jwt_extended import jwt_required
from flask_jwt_extended import JWTManager
from datetime import timedelta
from email.mime.text import MIMEText

from apscheduler.schedulers.background import BackgroundScheduler


# Flask app configurations
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_KEY")
app.config["JWT_TOKEN_LOCATION"] = ["headers"]
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = False
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=7)
jwt = JWTManager(app)

# Flask app configurations for Jenga API
app.config["JENGA_CONSUMER_KEY"] = "CONSUMER_KEY"
app.config["JENGA_CONSUMER_SECRET"] = "CONSUMER_SECRET"
app.config["JENGA_ENV"] = "sandbox"  # Change to 'production' when live
app.config["JENGA_BASE_URL"] = (
    "https://uat.finserve.africa/v3-apis/payment-api/v3.0/stkussdpush/initiate"  # Update this for production
)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")

# Flask app configurations
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY")
app.config["JWT_TOKEN_LOCATION"] = ["headers"]
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = False
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=7)
jwt = JWTManager(app)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URI")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=14)


# redis_host = os.getenv('REDIS_HOST', 'localhost')
# redis_port = os.getenv('REDIS_PORT', 6379)

# redis_client = redis.Redis(host=redis_host, port=redis_port)


_jwks_client = None


def _get_jwks_client():
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(CLERK_JWKS_URL, cache_keys=True)
    return _jwks_client


def verify_clerk_token(token: str) -> dict:
    client = _get_jwks_client()
    signing_key = client.get_signing_key_from_jwt(token)
    return pyjwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        options={"verify_aud": False},
    )


@jwt.user_identity_loader
def user_identity_lookup(user):
    return user  # Assuming 'user.id' is a scalar value like an integer


@jwt.user_lookup_loader
def user_lookup_callback(_jwt_header, jwt_data):
    user_id = jwt_data["sub"]  # This should be the user ID directly, not a dictionary
    print(user_id)

    return (
        Driver.query.filter_by(id=user_id).one_or_none()
        or Customer.query.filter_by(id=user_id).one_or_none()
    )


passkey = os.environ.get("MPESA_PASSKEY")
scheduler = BackgroundScheduler()


def check_pending_orders():
    with app.app_context():
        cutoff_time = datetime.utcnow() - timedelta(seconds=15)
        pending_orders = Order.query.filter(
            Order.status == "Pending", Order.created_at <= cutoff_time
        ).all()

        for order in pending_orders:
            order.status = "Declined"
            order.declined_drivers.append(order.driver_id)
            db.session.commit()
            reassign_order_to_next_driver(order)


def reassign_order_to_next_driver(order):
    drivers = Driver.query.filter(Driver.online == 'online', Driver.car_type == order.vehicle_type).all()
    nearest_driver = None
    min_distance = float("inf")
    for driver in drivers:
        if driver.id in order.declined_drivers:
            continue
        driver_distance = haversine(
            order.user_lat, order.user_lng, driver.latitude, driver.longitude
        )
        if driver_distance < min_distance:
            min_distance = driver_distance
            nearest_driver = driver

    if not nearest_driver:
        db.session.delete(order)
        db.session.commit()
        print(f"No available drivers nearby for order {order.id}, order deleted")
    else:
        order.driver_id = nearest_driver.id
        order.status = "Pending"
        db.session.commit()
        print(f"Order {order.id} reassigned to driver {nearest_driver.name}")
        if nearest_driver.fcm_token:
            km = round(order.distance or 0, 1)
            cost = int(order.total_cost or 0)
            send_expo_push(
                token=nearest_driver.fcm_token,
                title="Swyft Driver",
                body=f"Incoming delivery · KSh {cost:,} · {km} km away",
                data={
                    "type": "incoming-order",
                    "orderId": order.id,
                    "order": {
                        "id": order.id,
                        "driver_id": order.driver_id,
                        "customer_id": order.customer_id,
                        "status": order.status,
                        "user_lat": order.user_lat,
                        "user_lng": order.user_lng,
                        "dest_lat": order.dest_lat,
                        "dest_lng": order.dest_lng,
                        "distance": order.distance,
                        "total_cost": order.total_cost,
                        "loaders": order.loaders,
                        "loader_cost": order.loader_cost,
                    },
                },
                category_id="incoming-order",
            )


def check_inactive_drivers():
    """Mark drivers offline if no heartbeat received for 10 minutes."""
    with app.app_context():
        cutoff = datetime.utcnow() - timedelta(minutes=10)
        stale = Driver.query.filter(
            Driver.online.in_(['online', 'in_transit']),
            Driver.last_heartbeat.isnot(None),
            Driver.last_heartbeat < cutoff,
        ).all()
        for driver in stale:
            driver.online = 'offline'
            print(f"[HEARTBEAT] driver {driver.id} marked offline — no heartbeat since {driver.last_heartbeat}")
        if stale:
            db.session.commit()


scheduler.add_job(check_pending_orders, "interval", seconds=15)
scheduler.add_job(check_inactive_drivers, "interval", minutes=2)
scheduler.start()


def generate_mpesa_token():
    consumer_key = os.environ.get("MPESA_CONSUMER_KEY")
    consumer_secret = os.environ.get("MPESA_CONSUMER_SECRET")

    # Combine consumer key and secret into a Base64-encoded string
    credentials = f"{consumer_key}:{consumer_secret}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    # Define the Mpesa OAuth URL
    mpesa_auth_url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"

    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/json",
    }

    # Request the token
    response = requests.get(mpesa_auth_url, headers=headers)
    if response.status_code == 200:
        return response.json().get("access_token")
    else:
        response.raise_for_status()


def generate_password(shortcode, passkey, timestamp):
    raw_string = f"{shortcode}{passkey}{timestamp}"
    return base64.b64encode(raw_string.encode()).decode()


def generate_timestamp():
    return datetime.now().strftime("%Y%m%d%H%M%S")


class MpesaPayment(Resource):
    def post(self):
        data = request.get_json()
        try:
            required_fields = [
                "Amount",
                "PartyA",
                "PartyB",
                "PhoneNumber",
                "CallBackURL",
                "AccountReference",
                "TransactionDesc",
            ]
            for field in required_fields:
                if field not in data:
                    return make_response(
                        {"error": f"Missing required field: {field}"}, 400
                    )

            # Define business short code and generate timestamp
            business_short_code = 174379
            timestamp = generate_timestamp()  # Generate timestamp BEFORE using it
            password = generate_password(business_short_code, passkey, timestamp)
            transaction_type = "CustomerPayBillOnline"

            # Extract other fields
            amount = data.get("Amount")
            party_a = "600981"
            party_b = "174379"
            phone_number = "254708374149"
            call_back_url = os.environ.get("MPESA_CALLBACK")
            account_reference = "CompanyXLTD"
            transaction_desc = "Payment of X"

            # Generate Mpesa token
            token = generate_mpesa_token()

            # Create request payload
            request_payload = {
                "BusinessShortCode": business_short_code,
                "Password": password,
                "Timestamp": timestamp,
                "TransactionType": transaction_type,
                "Amount": amount,
                "PartyA": party_a,
                "PartyB": party_b,
                "PhoneNumber": phone_number,
                "CallBackURL": call_back_url,
                "AccountReference": account_reference,
                "TransactionDesc": transaction_desc,
            }

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            # Send API request
            response = requests.post(
                "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest",
                headers=headers,
                json=request_payload,
            )

            if response.status_code == 200:
                return make_response(
                    {
                        "message": "Payment initiated successfully",
                        "data": response.json(),
                    },
                    200,
                )
            else:
                return make_response(
                    {"error": "Payment initiation failed", "details": response.json()},
                    400,
                )

        except requests.exceptions.RequestException as e:
            return make_response({"error": "Request failed", "details": str(e)}, 500)
        except Exception as e:
            return make_response({"error": "An error occurred", "details": str(e)}, 500)


api.add_resource(MpesaPayment, "/process-payment")


class ReceiveCallback(Resource):
    # This endpoint receives the callback from mpesa after payment.
    def post(self):
        callback_data = request.get_json()
        try:
            if not callback_data:
                return make_response({"error": "No callback data received"}, 400)

            result_code = (
                callback_data.get("Body", {}).get("stkCallback", {}).get("ResultCode")
            )
            result_desc = (
                callback_data.get("Body", {}).get("stkCallback", {}).get("ResultDesc")
            )
            merchant_request_id = (
                callback_data.get("Body", {})
                .get("stkCallback", {})
                .get("MerchantRequestID")
            )
            checkout_request_id = (
                callback_data.get("Body", {})
                .get("stkCallback", {})
                .get("CheckoutRequestID")
            )
            callback_metadata = (
                callback_data.get("Body", {})
                .get("stkCallback", {})
                .get("CallbackMetadata", {})
                .get("Item", [])
            )

            metadata_dict = {
                item.get("Name"): item.get("Value") for item in callback_metadata
            }
            amount = metadata_dict.get("Amount")
            mpesa_receipt_number = metadata_dict.get("MpesaReceiptNumber")
            balance = metadata_dict.get("Balance")
            transaction_date = metadata_dict.get("TransactionDate")
            phone_number = metadata_dict.get("PhoneNumber")

            return make_response({"message": "Callback received successfully"}, 200)

        except Exception as e:
            # Return an error response
            return make_response(
                {
                    "error": "An error occurred while processing the callback",
                    "details": str(e),
                },
                500,
            )


api.add_resource(ReceiveCallback, "/payment-callback")


import hmac as _hmac
import hashlib as _hashlib

LIPANA_BASE = "https://api.lipana.dev/v1"
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def send_expo_push(token: str, title: str, body: str, data: dict = None, category_id: str = None):
    if not token:
        return
    payload = {
        "to": token,
        "title": title,
        "body": body,
        "sound": "bell",
        "priority": "high",
        "data": data or {},
        "channelId": "incoming-order",
    }
    if category_id:
        payload["categoryId"] = category_id
    try:
        resp = requests.post(
            EXPO_PUSH_URL,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            json=payload,
            timeout=10,
        )
        print(f"[EXPO PUSH] status={resp.status_code} response={resp.text[:300]}")
    except Exception as e:
        print(f"[EXPO PUSH] error: {e}")


@app.route("/payments/stk-push", methods=["POST"])
@jwt_required()
def lipana_stk_push():
    try:
        data = request.get_json(force=True) or {}
        phone = data.get("phone", "").strip()
        order_id = data.get("order_id")
        provided_amount = data.get("amount")
        description = data.get("description", "transport")
        print(f"[STK PUSH] phone='{phone}' order_id='{order_id}' amount={provided_amount} description={description}")

        if not phone:
            return make_response({"error": "phone is required"}, 400)

        if phone.startswith("0"):
            phone = "+254" + phone[1:]
        elif phone.startswith("254") and not phone.startswith("+"):
            phone = "+" + phone
        print(f"[STK PUSH] normalized phone='{phone}'")

        lipana_key = os.environ.get("LIPANA_SECRET_KEY")
        if not lipana_key:
            return make_response({"error": "Payment service not configured"}, 500)

        identity = get_jwt_identity()
        caller_id = identity.get("id") if isinstance(identity, dict) else identity

        # Determine amount and link to order if available
        order = None
        if provided_amount:
            amount = max(10, int(provided_amount))
        else:
            if not order_id:
                return make_response({"error": "order_id or amount is required"}, 400)
            order = Order.query.filter_by(id=order_id).first()
            if not order:
                print(f"[STK PUSH] order not found: '{order_id}'")
                return make_response({"error": "Order not found"}, 404)
            amount = max(10, int(order.total_cost))

        payload = {"phone": phone, "amount": amount}
        print(f"[STK PUSH] calling Lipana payload={payload}")

        resp = requests.post(
            f"{LIPANA_BASE}/transactions/push-stk",
            headers={"x-api-key": lipana_key, "Content-Type": "application/json"},
            json=payload,
            timeout=15,
        )
        print(f"[STK PUSH] Lipana status={resp.status_code} body={resp.text[:500]}")

        if not resp.ok:
            return make_response({"error": "Lipana error", "details": resp.text}, resp.status_code)

        result = resp.json()
        tx_id = result.get("data", {}).get("transactionId")
        print(f"[STK PUSH] transactionId='{tx_id}'")

        if order and tx_id:
            order.lipana_tx_id = tx_id
            db.session.commit()
        elif tx_id:
            # Non-order payment (e.g. viewing fee) — record in payments table
            customer = Customer.query.filter_by(id=caller_id).first()
            new_payment = Payment(
                id=str(uuid.uuid4()),
                customer_id=caller_id if customer else None,
                driver_id=None,
                amount=amount,
                description=description,
                lipana_tx_id=tx_id,
                status="pending",
            )
            db.session.add(new_payment)
            db.session.commit()

        return make_response(result, 200)

    except Exception as e:
        print(f"[STK PUSH] exception: {e}")
        return make_response({"error": "Failed to initiate payment", "details": str(e)}, 500)


@app.route("/payments/status", methods=["GET"])
@jwt_required()
def get_payment_status():
    tx_id = request.args.get("tx_id", "").strip()
    if not tx_id:
        return make_response({"error": "tx_id required"}, 400)
    payment = Payment.query.filter_by(lipana_tx_id=tx_id).first()
    status = payment.status if payment else "pending"
    return make_response({"status": status}, 200)


@app.route("/payments/lipana-webhook", methods=["POST"])
def lipana_webhook():
    payload = request.get_data()
    signature = request.headers.get("X-Lipana-Signature", "")
    webhook_secret = os.environ.get("LIPANA_WEBHOOK_SECRET", "")

    if signature and webhook_secret:
        expected = _hmac.new(
            webhook_secret.encode(), payload, _hashlib.sha256
        ).hexdigest()
        if not _hmac.compare_digest(signature, expected):
            return make_response({"error": "Invalid signature"}, 401)

    data = request.get_json(force=True) or {}
    event = data.get("event")
    event_data = data.get("data", {})

    if event == "payment.success":
        tx_id = event_data.get("transactionId") or event_data.get("transaction_id")
        print(f"[WEBHOOK] payment.success tx_id='{tx_id}'")
        if tx_id:
            # Commission payment — pending Payment row exists with this tx_id
            payment = Payment.query.filter_by(lipana_tx_id=tx_id).first()
            if payment and payment.status == "pending":
                payment.status = "completed"
                payment.timestamp = datetime.utcnow()
                db.session.commit()
                print(f"[WEBHOOK] commission payment '{tx_id}' completed for driver '{payment.driver_id}'")

                driver = Driver.query.get(payment.driver_id)
                if driver:
                    driver.commission_status = "cleared"
                    db.session.commit()
                    if driver.fcm_token:
                        send_expo_push(
                            token=driver.fcm_token,
                            title="Commission Cleared",
                            body=f"KES {int(payment.amount):,} commission paid. You can now accept orders.",
                            data={"type": "commission_cleared", "amount": payment.amount},
                        )

            # Order payment — order has this lipana_tx_id
            order = Order.query.filter_by(lipana_tx_id=tx_id).first()
            if order:
                order.is_paid = True
                db.session.commit()
                print(f"[WEBHOOK] order '{order.id}' marked as paid, driver_id='{order.driver_id}'")

                if order.driver_id:
                    driver = Driver.query.filter_by(id=order.driver_id).first()
                    if driver and driver.fcm_token:
                        amount = int(order.total_cost) if order.total_cost else 0
                        send_expo_push(
                            token=driver.fcm_token,
                            title="Payment Received",
                            body=f"KES {amount:,} has been paid for your delivery.",
                            data={"type": "payment_received", "order_id": order.id, "amount": amount},
                        )
                    else:
                        print(f"[WEBHOOK] driver not found or no fcm_token for driver_id='{order.driver_id}'")

    return make_response({"received": True}, 200)


@app.route("/driver/pay-commission", methods=["POST"])
@jwt_required()
def pay_commission():
    driver_id = get_jwt_identity()
    data = request.get_json(force=True) or {}
    raw_phone = data.get("phone", "").strip()

    print(f"[PAY-COMMISSION] >>> request  driver='{driver_id}'  raw_phone='{raw_phone}'")

    if not raw_phone:
        return make_response({"error": "phone is required"}, 400)

    # Normalize to 254XXXXXXXXX (no + — Lipana expects this format)
    phone = raw_phone
    if phone.startswith("+"):
        phone = phone[1:]
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    print(f"[PAY-COMMISSION] normalized phone='{phone}'")

    try:
        # Commission is owed on ALL completed orders (cash + app-paid)
        total_completed = (
            db.session.query(db.func.sum(Order.total_cost))
            .filter(
                Order.driver_id == driver_id,
                Order.status == "completed",
            )
            .scalar() or 0.0
        )
        paid = (
            db.session.query(db.func.sum(Payment.amount))
            .filter(Payment.driver_id == driver_id, Payment.status == "completed")
            .scalar() or 0.0
        )
        rate_setting = AppSettings.query.first()
        commission_rate = Decimal(str(rate_setting.commission_rate)) if rate_setting else Decimal("0.18")
        commission = float(Decimal(str(total_completed)) * commission_rate)
        outstanding = commission - float(paid)

        print(f"[PAY-COMMISSION] total_completed={total_completed}  commission_paid={paid}  rate={commission_rate}  commission_owed={commission}  outstanding={outstanding}")

        if outstanding <= 0:
            print(f"[PAY-COMMISSION] no outstanding commission — returning 200 early")
            return make_response({"message": "No outstanding commission", "amount": 0}, 200)

        amount = max(10, int(outstanding))

        lipana_key = os.environ.get("LIPANA_SECRET_KEY")
        print(f"[PAY-COMMISSION] LIPANA_SECRET_KEY set={bool(lipana_key)}  prefix='{(lipana_key or '')[:16]}'")

        if not lipana_key:
            return make_response({"error": "Payment service not configured"}, 500)

        lipana_url = f"{LIPANA_BASE}/transactions/push-stk"
        lipana_payload = {"phone": phone, "amount": amount}
        print(f"[PAY-COMMISSION] >>> Lipana POST {lipana_url}")
        print(f"[PAY-COMMISSION] >>> payload={lipana_payload}")

        resp = requests.post(
            lipana_url,
            headers={"x-api-key": lipana_key, "Content-Type": "application/json"},
            json=lipana_payload,
            timeout=15,
        )
        print(f"[PAY-COMMISSION] <<< Lipana status={resp.status_code}")
        print(f"[PAY-COMMISSION] <<< Lipana body={resp.text}")

        if not resp.ok:
            print(f"[PAY-COMMISSION] Lipana error {resp.status_code}: {resp.text}")
            return make_response({"error": "Payment initiation failed", "details": resp.text}, resp.status_code)

        result = resp.json()
        tx_id = result.get("data", {}).get("transactionId")
        print(f"[PAY-COMMISSION] transactionId='{tx_id}'  full_result={result}")

        new_payment = Payment(
            id=str(uuid.uuid4()),
            driver_id=driver_id,
            amount=amount,
            lipana_tx_id=tx_id,
            status="pending",
        )
        db.session.add(new_payment)
        db.session.commit()
        print(f"[PAY-COMMISSION] pending Payment row saved  id='{new_payment.id}'  tx_id='{tx_id}'  amount={amount}")

        return make_response({"message": "STK push sent", "amount": amount, "tx_id": tx_id}, 200)

    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"[PAY-COMMISSION] EXCEPTION: {e}")
        print(traceback.format_exc())
        return make_response({"error": "Failed to initiate payment", "details": str(e)}, 500)


class Home(Resource):
    def get(self):
        return {"message": "Welcome to Swyft"}


api.add_resource(Home, "/")


class SignUp(Resource):
    def post(self):
        data = request.get_json()

        id = data.get("id")
        full_name = data.get("name")
        email = data.get("email")
        phone_number = data.get("phone")
        password = data.get("password")
        provider = data.get("provider")

        existing_user = Customer.query.filter(
            (Customer.email == email) | (Customer.phone == phone_number if phone_number else False)
        ).first()

        if existing_user:
            if existing_user.email == email:
                return make_response(
                    {"error": "Email already registered, kindly login"}, 400
                )
            if phone_number and existing_user.phone == phone_number:
                return make_response({"error": "Phone number already registered"}, 400)

        unique_id = str(uuid.uuid4())
        while Customer.query.filter_by(id=unique_id).first():
            unique_id = str(uuid.uuid4())

        # For OAuth users, use a unique placeholder phone and a random password hash
        if not phone_number:
            phone_number = f"OAUTH_{unique_id[:12]}"
        if not password:
            import secrets
            password = secrets.token_hex(32)

        try:
            new_user = Customer(
                id=unique_id, name=full_name, email=email, phone=phone_number
            )

            new_user.password_hash = password

            db.session.add(new_user)
            db.session.commit()

            access_token = create_access_token(
                identity={"id": new_user.id, "type": "customer"}
            )
            refresh_token = create_refresh_token(
                identity={"id": new_user.id, "type": "customer"}
            )

            response_dict = new_user.to_dict()

            response = make_response(
                {
                    "message": "User created successfully",
                    "user": response_dict,
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                },
                201,
            )

            return response

        except Exception as e:
            db.session.rollback()
            return make_response({"error": str(e)}, 500)


api.add_resource(SignUp, "/signup")


class Login(Resource):
    def post(self):
        data = request.get_json()
        print(f"[LOGIN] payload keys: {list(data.keys()) if data else 'None'}")

        email = data.get("email")
        password = data.get("password")
        provider = data.get("provider")
        print(f"[LOGIN] email='{email}'  provider='{provider}'  has_password={bool(password)}")

        existing_user = Customer.query.filter(Customer.email == email).first()
        print(f"[LOGIN] user found: {bool(existing_user)}  id={existing_user.id if existing_user else 'n/a'}")

        if not existing_user:
            print(f"[LOGIN] 400 — email not found")
            return make_response(
                {"error": "Email address not found in our records, create account"}, 400
            )

        if provider != "google":
            pw_ok = bool(password) and bcrypt.check_password_hash(existing_user._password_hash, password)
            print(f"[LOGIN] password check: {pw_ok}")
            if not pw_ok:
                return make_response({"error": "Incorrect password, please try again"}, 400)

        access_token = create_access_token(identity=existing_user.id)
        refresh_token = create_refresh_token(identity=existing_user.id)
        print(f"[LOGIN] 200 — token issued for user {existing_user.id}")

        response = {
            "access_token": access_token,
            "user": existing_user.to_dict(),
            "refresh_token": refresh_token,
            "message": "Login successful",
        }

        return make_response(response, 200)


api.add_resource(Login, "/login")


class GoogleAuth(Resource):
    def post(self):
        data = request.get_json()
        session_token = data.get("session_token")
        email         = data.get("email")
        name          = data.get("name")
        image_url     = data.get("image_url", "")

        if not session_token or not email:
            return make_response({"error": "session_token and email are required"}, 400)

        try:
            payload = verify_clerk_token(session_token)
        except Exception as e:
            return make_response({"error": "Invalid session token", "detail": str(e)}, 401)

        clerk_id = payload.get("sub")

        customer = (
            Customer.query.filter_by(clerk_id=clerk_id).first()
            or Customer.query.filter_by(email=email).first()
        )

        if customer:
            updated = False
            if not customer.clerk_id:
                customer.clerk_id = clerk_id
                updated = True
            if image_url and customer.profile_picture != image_url:
                customer.profile_picture = image_url
                updated = True
            if updated:
                db.session.commit()
        else:
            import secrets
            unique_id = str(uuid.uuid4())
            while Customer.query.filter_by(id=unique_id).first():
                unique_id = str(uuid.uuid4())

            placeholder_phone = f"OAUTH_{unique_id[:12]}"
            while Customer.query.filter_by(phone=placeholder_phone).first():
                placeholder_phone = f"OAUTH_{str(uuid.uuid4())[:12]}"

            try:
                customer = Customer(
                    id=unique_id,
                    name=name or email.split("@")[0],
                    email=email,
                    phone=placeholder_phone,
                    clerk_id=clerk_id,
                    profile_picture=image_url,
                )
                customer.password_hash = secrets.token_hex(32)
                db.session.add(customer)
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                return make_response({"error": "Account creation failed, please try again"}, 500)

        access_token  = create_access_token(identity=customer.id)
        refresh_token = create_refresh_token(identity=customer.id)

        return make_response({
            "message": "Login successful",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": customer.to_dict(),
        }, 200)


api.add_resource(GoogleAuth, "/auth/google")


class CheckSession(Resource):
    @jwt_required()
    def get(self):
        return make_response(current_user.to_dict(), 200)


api.add_resource(CheckSession, "/check_session", endpoint="check_session")


@app.route("/profile/phone", methods=["PATCH"])
@jwt_required()
def update_customer_phone():
    try:
        data = request.get_json(force=True) or {}
        phone = data.get("phone", "").strip()
        print(f"[PHONE UPDATE] raw phone received: '{phone}'")

        if not phone:
            print("[PHONE UPDATE] rejected: empty phone")
            return make_response({"error": "Phone number is required"}, 400)

        if phone.startswith("+"):
            phone = phone[1:]
        if phone.startswith("0"):
            phone = "254" + phone[1:]
        print(f"[PHONE UPDATE] normalized phone: '{phone}'")

        identity = get_jwt_identity()
        customer_id = identity.get("id") if isinstance(identity, dict) else identity
        print(f"[PHONE UPDATE] customer_id from JWT: '{customer_id}'")

        customer = Customer.query.filter_by(id=customer_id).first()
        if not customer:
            print(f"[PHONE UPDATE] customer not found for id: '{customer_id}'")
            return make_response({"error": "User not found"}, 404)

        existing = Customer.query.filter(
            Customer.phone == phone, Customer.id != customer_id
        ).first()
        if existing:
            print(f"[PHONE UPDATE] phone '{phone}' already used by customer '{existing.id}'")
            return make_response({"error": "Phone number already in use"}, 400)

        customer.phone = phone
        db.session.commit()
        print(f"[PHONE UPDATE] success for customer '{customer_id}', phone set to '{phone}'")
        return make_response({"user": customer.to_dict()}, 200)

    except Exception as e:
        db.session.rollback()
        print(f"[PHONE UPDATE] exception: {e}")
        return make_response({"error": str(e)}, 500)


class TokenRefresh(Resource):
    @jwt_required(refresh=True)
    def post(self):
        current_user = get_jwt_identity()
        new_access_token = create_access_token(identity=current_user)

        response = {
            "access_token": new_access_token,
            "message": "Token refreshed successfully",
        }

        return make_response(response, 200)


api.add_resource(TokenRefresh, "/refresh")


def generate_otp(email, purpose="reset"):
    # Generate a time-based OTP using pyotp
    otp = str(pyotp.TOTP(pyotp.random_base32()).now())  # generate a 6-digit OTP
    expiry = datetime.utcnow() + timedelta(minutes=5)  # OTP expiration time

    msg = MIMEText(f"Your OTP code is {otp}")
    msg["Subject"] = "OTP Verification"
    msg["From"] = SMTP_USERNAME
    msg["To"] = email

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.sendmail(SMTP_USERNAME, email, msg.as_string())

    # Clean up old OTPs for the same email
    OTP.query.filter_by(driver_email=email).delete()
    print(SMTP_USERNAME)
    print(SMTP_PASSWORD)
    # Create new OTP record
    new_otp = OTP(driver_email=email, code=otp, purpose=purpose, expires_at=expiry)
    db.session.add(new_otp)
    db.session.commit()

    return otp


@app.route("/send-otp", methods=["POST"])
def send_otp():
    data = request.get_json()
    email = data.get("email")

    if not email:
        return make_response({"error": "Email is required"}, 400)

    user = Customer.query.filter_by(email=email).first()
    if not user:
        return make_response({"error": "User not found"}, 404)

    otp = generate_otp(email, purpose="reset")

    return make_response({"success": "OTP sent successfully"}, 200)


@app.route("/signup-otp", methods=["POST"])
def signup_otp():
    data = request.get_json()
    email = data.get("email")

    if not email:
        return make_response({"error": "Email required"}, 404)

    existing_user = Customer.query.filter_by(email=email).first()
    if existing_user:
        return make_response({"error": "Account already exists with this email"}, 400)

    try:
        generate_otp(email, purpose="signup")
        return make_response({"success": "OTP sent successfully"}, 200)
    except Exception as e:
        return make_response({"error": str(e)}, 500)


@app.route("/verify-signup-otp", methods=["POST"])
def verify_signup_otp():
    data = request.get_json()
    email = data.get("email")
    otp = data.get("otp")

    if not email or not otp:
        return make_response({"error": "Email and OTP are required"}, 400)

    # Find the OTP record for the email and OTP provided
    otp_record = OTP.query.filter_by(driver_email=email, code=otp).first()

    if not otp_record:
        return make_response({"error": "Invalid OTP"}, 400)

    # Check if the OTP has expired
    if otp_record.expires_at < datetime.utcnow():
        return make_response({"error": "OTP has expired"}, 400)

    # Mark the OTP as verified
    otp_record.verified = True
    db.session.commit()

    return make_response({"success": "OTP verified successfully"}, 200)

# driver forgot password endpoint
@app.route("/driver/forgot-password", methods=["POST"])
def driver_forgot_password():
    data = request.get_json()
    email = data.get("email")

    if not email:
        return make_response({"error": "Email is required"}, 400)

    user = Driver.query.filter_by(email=email).first()
    if not user:
        return make_response({"error": "No driver account found with that email"}, 404)

    try:
        generate_otp(email, purpose="reset")
        return make_response({"success": "OTP sent to your email"}, 200)
    except Exception as e:
        return make_response({"error": str(e)}, 500)


@app.route("/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json()
    email = data.get("email")
    otp = data.get("otp")
    new_password = data.get("newPassword")

    if not email or not otp or not new_password:
        return make_response(
            {"error": "Email, OTP, and new password are required"}, 400
        )

    # Find the OTP record for the email and OTP provided
    otp_record = OTP.query.filter_by(driver_email=email, code=otp).first()

    if not otp_record:
        return make_response({"error": "Invalid OTP"}, 400)

    # Check if the OTP has expired
    if otp_record.expires_at < datetime.utcnow():
        return make_response({"error": "OTP has expired"}, 400)

    # Find the user and update the password
    user = Driver.query.filter_by(email=email).first()
    if not user:
        return make_response({"error": "User not found"}, 404)

    user.password_hash = new_password  # Update the password field
    db.session.commit()

    # Mark the OTP as verified
    otp_record.verified = True
    db.session.commit()

    return make_response({"success": "Password reset successfully"}, 200)


# @app.route("/driver/kyc", methods=["PATCH", "PUT"])
# @jwt_required()
# def driver_kyc():
#     data = request.get_json()
#     id = data.get("id")
#     if not id:
#         return make_response({"error": "Driver ID is required"}, 400)

#     driver = Driver.query.filter_by(id=id).first()
#     if not driver:
#         return make_response({"error": "Driver not found"}, 404)

#     driver.driving_license = data.get("drivingLicenseURL")
#     driver.national_id_back = data.get("nationalIDBack")
#     driver.national_id_front = data.get("nationalIDFront")
#     driver.vehicle_registration = data.get("vehicleRegistration")
#     driver.car_insurance = data.get("CarInsurance")
#     driver.vehicle_picture_front = data.get("vehiclePictureFront")
#     driver.vehicle_picture_back = data.get("vehiclePictureBack")
#     driver.inspection_report = data.get("inspectionReport")


#     db.session.commit()
#     response = make_response(driver.to_dict(), 200)

#     return response


@app.route("/driver/verify", methods=["PATCH", "PUT"])
def verify_driver():
    try:
        data = request.get_json()  # Get JSON from the request body
        if not data:
            return {"error": "Missing JSON body"}, 400

        driver_id = data.get("id")  # Get the ID from the request
        if not driver_id:
            return {"error": "Driver ID is required"}, 400

        driver = Driver.query.get(
            driver_id
        )  # Assuming you're using a UUID as primary key
        if not driver:
            return {"error": "Driver not found"}, 404

        driver.verified = data.get("verified", True)  # Update verification status
        db.session.commit()

        return {"message": "Driver verified", "driver": driver.to_dict()}, 200

    except Exception as e:
        print(f"Error verifying driver: {str(e)}")  # Logs for debugging
        return {"error": "Internal server error"}, 500


@app.route("/driver/unverify", methods=["PATCH", "PUT"])
def unverify_driver():
    data = request.get_json()
    id = data.get("id")
    if not id:
        return make_response({"error": "Driver ID is required"}, 400)

    driver = Driver.query.filter_by(id=id).first()
    if not driver:
        return make_response({"error": "Driver not found"}, 404)

    driver.verified = False
    db.session.commit()
    return make_response(driver.to_dict(), 200)


@app.route("/driver/check-verification", methods=["POST"])
def check_verification():
    data = request.get_json()
    id = data.get("id")
    if not id:
        return make_response({"error": "Driver ID is required"}, 400)

    driver = Driver.query.filter_by(id=id).first()
    if not driver:
        return make_response({"error": "Driver not found"}, 404)

    verification_status = driver.verified  # Directly access the verification attribute

    return make_response({"verification": verification_status}, 200)


@app.route("/driver/signup/update-documents", methods=["POST"])
def update_documents():
    data = request.get_json()

    driver_id = data.get("id")
    documents = data.get("documents")

    if not driver_id or not documents:
        return jsonify({"error": "Driver ID and documents are required"}), 400

    driver = Driver.query.get(driver_id)

    if not driver:
        return jsonify({"error": "Driver not found"}), 404

    # Map the camelCase keys the driver app sends to the snake_case columns.
    # Only assign keys that are actually present so a partial update never
    # wipes existing links.
    doc_field_map = {
        "drivingLicense": "driving_license",
        "nationalIDFront": "national_id_front",
        "nationalIDBack": "national_id_back",
        "psvBadge": "psv_badge",
        "vehicleRegistration": "vehicle_registration",
        "vehiclePictureFront": "vehicle_picture_front",
        "vehiclePictureBack": "vehicle_picture_back",
        "psvCarInsurance": "car_insurance",
        "inspectionReport": "inspection_report",
        "passportPhoto": "passport_photo",
        "certificateOfGoodConduct": "certificate_conduct",
        "companyRegistrationCertificate": "company_reg_certificate",
        "kra": "kra",
    }

    for incoming_key, column in doc_field_map.items():
        if incoming_key in documents:
            setattr(driver, column, documents[incoming_key])

    db.session.commit()

    return jsonify({"message": "Documents updated successfully"}), 200


@app.route("/driver/request-login-otp", methods=["POST"])
def driver_request_login_otp():
    data = request.get_json()
    email = data.get("email", "").strip().lower()

    if not email:
        return make_response({"error": "Email is required"}, 400)

    driver = Driver.query.filter_by(email=email).first()
    if not driver:
        return make_response({"error": "No driver account found with this email"}, 404)

    try:
        generate_otp(email, purpose="login")
        return make_response({"success": "OTP sent to your email"}, 200)
    except Exception as e:
        return make_response({"error": str(e)}, 500)


@app.route("/driver/verify-login-otp", methods=["POST"])
def driver_verify_login_otp():
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    otp_code = data.get("otp", "").strip()
    fcm_token = data.get("fcm_token", "")

    if not email or not otp_code:
        return make_response({"error": "Email and OTP are required"}, 400)

    driver = Driver.query.filter_by(email=email).first()
    if not driver:
        return make_response({"error": "Driver not found"}, 404)

    otp_record = OTP.query.filter_by(driver_email=email, code=otp_code, purpose="login").first()
    if not otp_record:
        return make_response({"error": "Invalid OTP code"}, 400)

    if otp_record.expires_at < datetime.utcnow():
        return make_response({"error": "OTP has expired. Please request a new one."}, 400)

    otp_record.verified = True
    if fcm_token:
        driver.fcm_token = fcm_token
    db.session.commit()

    access_token = create_access_token(identity=driver.id)
    refresh_token = create_refresh_token(identity=driver.id)

    return make_response({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": driver.to_dict(),
        "message": "Login successful",
    }, 200)


class DriverLogin(Resource):
    def post(self):
        data = request.get_json()

        email = data.get("email")
        password = data.get("password")

        existing_driver = Driver.query.filter(Driver.email == email).first()

        if not existing_driver:
            return make_response(
                {"error": "Email address not found in our records, create account"}, 400
            )

        if not bcrypt.check_password_hash(existing_driver._password_hash, password):
            return make_response({"error": "Incorrect password, please try again"}, 400)

        fcm_token = data.get("fcm_token")
        if fcm_token:
            existing_driver.fcm_token = fcm_token
            db.session.commit()

        access_token = create_access_token(identity=existing_driver.id)
        refresh_token = create_refresh_token(identity=existing_driver.id)

        response = {
            "access_token": access_token,
            "user": existing_driver.to_dict(),
            "refresh_token": refresh_token,
            "message": "Login successful",
        }

        return make_response(response, 200)


api.add_resource(DriverLogin, "/driver/login")


@app.route("/customer/push-token", methods=["PUT"])
@jwt_required()
def update_customer_push_token():
    customer_id = get_jwt_identity()
    if isinstance(customer_id, dict):
        customer_id = customer_id.get("id")
    data = request.get_json(force=True) or {}
    push_token = data.get("push_token")
    if not push_token:
        return make_response({"error": "push_token required"}, 400)
    customer = Customer.query.get(customer_id)
    if not customer:
        return make_response({"error": "Customer not found"}, 404)
    customer.push_token = push_token
    db.session.commit()
    return make_response({"message": "Token updated"}, 200)


@app.route("/driver/fcm-token", methods=["PUT"])
@jwt_required()
def update_driver_fcm_token():
    driver_id = get_jwt_identity()
    data = request.get_json()
    fcm_token = data.get("fcm_token")
    if not fcm_token:
        return make_response({"error": "fcm_token required"}, 400)
    driver = Driver.query.get(driver_id)
    if not driver:
        return make_response({"error": "Driver not found"}, 404)
    driver.fcm_token = fcm_token
    db.session.commit()
    return make_response({"message": "Token updated"}, 200)

@app.route("/driver/orders", methods=["POST"])
def driver_orders():
    data = request.get_json()

    driver_id = data.get("id")
    if not driver_id:
        return make_response({"error": "Driver ID is required"}, 400)

    limit = int(data.get("limit", 10))
    offset = int(data.get("offset", 0))

    query = Order.query.filter_by(driver_id=driver_id).order_by(Order.created_at.desc())
    total = query.count()
    orders = query.offset(offset).limit(limit).all()

    if not orders and offset == 0:
        return make_response({"message": "No orders found"}, 200)

    response = [order.to_dict() for order in orders]
    return make_response({"orders": response, "total": total, "has_more": (offset + limit) < total}, 200)

@app.route("/driver_delete/<driver_id>", methods=['DELETE'])
@jwt_required()
def delete_driver(driver_id):
    identity = get_jwt_identity()
    # A driver may only delete their own account.
    if str(identity) != str(driver_id):
        return make_response({"error": "Forbidden"}, 403)
    driver = Driver.query.filter_by(id=driver_id).one_or_none()
    if not driver:
        return make_response({"error": "Driver not found"}, 404)
    try:
        _purge_driver_record(driver)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return make_response({"error": "Failed to delete account", "detail": str(e)}, 500)
    return make_response({"message": "Driver deleted successfully"}, 200)


def _purge_customer_record(customer):
    """Delete a customer and the data tied to their identity.

    The models declare foreign keys without ON DELETE CASCADE, so dependent
    rows must be removed first or the delete violates a constraint.
    """
    cid = customer.id
    order_ids = [o.id for o in Order.query.filter_by(customer_id=cid).all()]
    if order_ids:
        Rating.query.filter(Rating.order_id.in_(order_ids)).delete(synchronize_session=False)
        Ride.query.filter(Ride.order_id.in_(order_ids)).delete(synchronize_session=False)
    Payment.query.filter_by(customer_id=cid).delete(synchronize_session=False)
    ScheduledMove.query.filter_by(customer_id=cid).delete(synchronize_session=False)
    Order.query.filter_by(customer_id=cid).delete(synchronize_session=False)
    Vehicle.query.filter_by(customer_id=cid).delete(synchronize_session=False)
    db.session.delete(customer)


def _purge_driver_record(driver):
    """Delete a driver and their personal data.

    Orders, payments and scheduled moves belong to customers too, so we keep
    those records but de-link the driver (set driver_id to NULL) rather than
    deleting another user's history. The driver's own vehicles and OTPs go.
    """
    did = driver.id
    Order.query.filter_by(driver_id=did).update({Order.driver_id: None}, synchronize_session=False)
    Payment.query.filter_by(driver_id=did).update({Payment.driver_id: None}, synchronize_session=False)
    ScheduledMove.query.filter_by(driver_id=did).update({ScheduledMove.driver_id: None}, synchronize_session=False)
    Vehicle.query.filter_by(driver_id=did).delete(synchronize_session=False)
    if driver.email:
        OTP.query.filter_by(driver_email=driver.email).delete(synchronize_session=False)
    db.session.delete(driver)


@app.route("/account", methods=["DELETE"])
@jwt_required()
def delete_my_account():
    """Customer self-service account & data deletion."""
    identity = get_jwt_identity()
    customer = Customer.query.filter_by(id=identity).one_or_none()
    if not customer:
        return make_response({"error": "Customer account not found"}, 404)
    try:
        _purge_customer_record(customer)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return make_response({"error": "Failed to delete account", "detail": str(e)}, 500)
    return make_response({"message": "Account and associated data deleted"}, 200)


@app.route("/driver/account", methods=["DELETE"])
@jwt_required()
def delete_my_driver_account():
    """Driver self-service account & data deletion."""
    identity = get_jwt_identity()
    driver = Driver.query.filter_by(id=identity).one_or_none()
    if not driver:
        return make_response({"error": "Driver account not found"}, 404)
    try:
        _purge_driver_record(driver)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return make_response({"error": "Failed to delete account", "detail": str(e)}, 500)
    return make_response({"message": "Driver account and associated data deleted"}, 200)


class OrderResource(Resource):
    @jwt_required()
    def get(self):
        current_user_id = get_jwt_identity()
        orders = Order.query.filter_by(customer_id=current_user_id).all()
        if not orders:
            return make_response({"message": "No orders found"}, 200)
        response = [order.to_dict() for order in orders]
        return make_response(response, 200)

    @jwt_required()
    def post(self):
        data = request.get_json()
        customer_id = get_jwt_identity()

        vehicle = data.get("vehicle")
        distance = data.get("distance")
        loaders = data.get("loaders")
        loader_cost = data.get("loaderCost")
        total_cost = data.get("totalCost")
        user_location = data.get("userLocation")
        destination = data.get("destination")
        time = data.get("time")

        if not all([user_location, destination]):
            return make_response(
                {"error": "Pickup and drop-off locations are required"}, 400
            )

        from_latitude = user_location.get("lat")
        from_longitude = user_location.get("lng")
        to_latitude = destination.get("lat")
        to_longitude = destination.get("lng")

        if not all([from_latitude, from_longitude, to_latitude, to_longitude]):
            return make_response(
                {"error": "Invalid coordinates provided for pickup or destination"}, 400
            )

        drivers = Driver.query.filter(Driver.online == 'online', Driver.car_type == vehicle).all()
        if not drivers:
            return make_response(
                {"error": "No available driver with the requested vehicle type"}, 404
            )

        try:
            nearest_driver = None
            min_distance = float("inf")

            for driver in drivers:
                driver_distance = haversine(
                    from_latitude, from_longitude, driver.latitude, driver.longitude
                )
                if driver_distance < min_distance:
                    min_distance = driver_distance
                    nearest_driver = driver

            if not nearest_driver:
                return make_response({"error": "No available drivers nearby"}, 404)

            unique_order_id = str(uuid.uuid4())
            while Order.query.filter_by(id=unique_order_id).first():
                unique_order_id = str(uuid.uuid4())

            rate_setting = AppSettings.query.first()
            commission_rate = rate_setting.commission_rate if rate_setting else 0.18
            total_cost = data.get("totalCost") or 0
            commission = round(total_cost * commission_rate, 2)

            new_order = Order(
                id=unique_order_id,
                customer_id=customer_id,
                vehicle_type=data.get("vehicle"),
                distance=data.get("distance"),
                loaders=data.get("loaders"),
                loader_cost=data.get("loaderCost"),
                total_cost=total_cost,
                user_lat=from_latitude,
                user_lng=from_longitude,
                dest_lat=to_latitude,
                dest_lng=to_longitude,
                time=data.get("time"),
                driver_id=nearest_driver.id,
                commission=commission,
            )
            db.session.add(new_order)
            db.session.commit()

            # Notify the assigned driver even when the app is backgrounded/killed
            if nearest_driver.fcm_token:
                km = round(data.get("distance") or 0, 1)
                cost = int(data.get("totalCost") or 0)
                send_expo_push(
                    token=nearest_driver.fcm_token,
                    title="New Delivery Request",
                    body=f"KSh {cost:,} · {km} km away",
                    data={
                        "type": "incoming-order",
                        "orderId": unique_order_id,
                        "order": new_order.to_dict(),
                    },
                    category_id="incoming-order",
                )

            return make_response(
                {
                    "message": "Order made successfully",
                    "order": new_order.to_dict(),
                    "nearest_driver": nearest_driver.to_dict(),
                },
                200,
            )

        except Exception as e:
            db.session.rollback()
            return make_response({"error": str(e)}, 500)

    @jwt_required()
    def put(self, order_id):
        """
        Use this endpoint for a driver to update the order status. When setting the status to "on_the_way"
        (indicating acceptance), we perform an atomic update. Upon successful acceptance, we notify all other
        broadcasted drivers in real time that the order is no longer available.
        """
        current_user_id = get_jwt_identity()

        order = Order.query.get(order_id)
        if not order:
            return make_response({"error": "Order not found"}, 404)

        # Basic authorization: For drivers, you might want to further ensure they're in the broadcast list.
        if hasattr(current_user, "car_type") and current_user.car_type:
            pass
        else:
            if order.customer_id != current_user_id:
                return make_response(
                    {"error": "Unauthorized to update this order"}, 403
                )

        data = request.get_json()
        new_status = data.get("status")

        valid_statuses = [
            "on_the_way",
            "arrived_at_customer",
            "on_the_way_to_destination",
            "completed",
            "cancelled",
        ]

        if new_status not in valid_statuses:
            return make_response({"error": "Invalid status value"}, 400)

        try:
            if new_status == "on_the_way":
                # Atomic update: only update if the order is still "Pending"
                result = Order.query.filter(
                    Order.id == order_id, Order.status == "Pending"
                ).update(
                    {
                        "status": "on_the_way",
                        "driver_id": current_user_id,
                        "accepted_at": datetime.utcnow(),
                    },
                    synchronize_session=False,
                )
                if result == 0:
                    db.session.rollback()
                    return make_response(
                        {"error": "Order already accepted by another driver"},
                        409,
                    )
            else:
                order.status = new_status
                if new_status in ('completed', 'cancelled'):
                    driver = Driver.query.get(order.driver_id)
                    if driver:
                        driver.online = 'online'
                if new_status == 'completed' and order.total_cost:
                    rate_setting = AppSettings.query.first()
                    commission_rate = rate_setting.commission_rate if rate_setting else 0.18
                    order.commission = round(order.total_cost * commission_rate, 2)

            db.session.commit()

            if new_status == "on_the_way":
                # Notify all other drivers that the order is no longer available.
                send_order_unavailable_notification(order_id, current_user_id)

            return make_response(
                {
                    "message": "Order status updated successfully",
                    "order": order.to_dict(),
                },
                200,
            )
        except Exception as e:
            db.session.rollback()
            return make_response({"error": str(e)}, 500)

    # @jwt_required()
    # def delete(self, order_id):
    #     current_user_id = get_jwt_identity()
    #     order = Order.query.get(order_id)
    #     if not order:
    #         return make_response({"error": "Order not found"}, 404)

    #     if order.customer_id != current_user_id:
    #         return make_response({"error": "Unauthorized to delete this order"}, 403)

    #     try:
    #         db.session.delete(order)
    #         db.session.commit()
    #         return make_response({"message": "Order deleted successfully"}, 200)
    #     except Exception as e:
    #         db.session.rollback()
    #         return make_response({"error": str(e)}, 500)


api.add_resource(OrderResource, "/orders", "/orders/<string:order_id>")


class DriverRides(Resource):
    @jwt_required()
    def get(self):
        current_user_id = get_jwt_identity()
        rides = Order.query.filter_by(driver_id=current_user_id)

        if not rides:
            return make_response({"message": "No rides found"}, 200)

        response = [ride.to_dict() for ride in rides]

        return make_response(response, 200)


api.add_resource(DriverRides, "/rides")


class DriverProfile(Resource):
    @jwt_required()
    def get(self):
        current_user_id = get_jwt_identity()
        driver = Driver.query.get(current_user_id)

        if not driver:
            return make_response({"message": "Driver not found"}, 404)

        response = driver.to_dict()

        # Avatar defaults to the verified passport photo when the driver
        # hasn't uploaded a separate profile picture.
        if not response.get("profile_picture"):
            response["profile_picture"] = driver.passport_photo

        return make_response(response, 200)

    @jwt_required()
    def put(self):
        current_user_id = get_jwt_identity()
        driver = Driver.query.get(current_user_id)

        if not driver:
            return make_response({"message": "Driver not found"}, 404)

        data = request.get_json(force=True) or {}

        # A verified driver may only override their display photo here.
        # Identity, vehicle and document fields are locked post-verification
        # and must go through an admin / re-verification flow.
        if "profile_picture" not in data:
            return make_response(
                {"error": "Only profile_picture can be updated"}, 400
            )

        driver.profile_picture = data["profile_picture"]

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return make_response({"error": str(e)}, 500)

        response = driver.to_dict()
        if not response.get("profile_picture"):
            response["profile_picture"] = driver.passport_photo

        return make_response(response, 200)


api.add_resource(DriverProfile, "/driver/profile")


class DriverEarnings(Resource):
    def options(self, driver_id):
        # Respond to preflight CORS request
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")  # Or specific domain
        response.headers.add(
            "Access-Control-Allow-Headers", "Content-Type,Authorization"
        )
        response.headers.add("Access-Control-Allow-Methods", "GET,OPTIONS")
        return response, 200

    def get(self, driver_id):
        response_headers = {
            "Access-Control-Allow-Origin": "*",  # Or restrict to your frontend URL
            "Content-Type": "application/json",
        }

        if not Driver.query.get(driver_id):
            return make_response(
                jsonify({"error": "Driver not found"}), 404, response_headers
            )

        try:
            # App-paid orders (customer paid through platform)
            app_orders_total = (
                db.session.query(db.func.sum(Order.total_cost))
                .filter(
                    Order.driver_id == driver_id,
                    Order.status == "completed",
                    Order.is_paid == True,
                )
                .scalar()
                or 0.0
            )

            # Cash orders (completed but customer paid driver directly)
            cash_orders_total = (
                db.session.query(db.func.sum(Order.total_cost))
                .filter(
                    Order.driver_id == driver_id,
                    Order.status == "completed",
                    (Order.is_paid == False) | (Order.is_paid == None),
                )
                .scalar()
                or 0.0
            )

            # Total commission the driver has already paid to Swyft
            total_commission_paid = (
                db.session.query(db.func.sum(Payment.amount))
                .filter(Payment.driver_id == driver_id, Payment.status == "completed")
                .scalar()
                or 0.0
            )
        except Exception as e:
            return make_response(
                jsonify({"error": "Database query failed", "details": str(e)}),
                500,
                response_headers,
            )

        app_orders_total = Decimal(app_orders_total)
        cash_orders_total = Decimal(cash_orders_total)
        total_commission_paid = Decimal(total_commission_paid)
        total_completed_earnings = app_orders_total + cash_orders_total

        rate = AppSettings.query.first()
        commission_rate = Decimal(str(rate.commission_rate)) if rate else Decimal("0.18")

        # Commission owed is based on ALL completed orders, minus what's already been paid to Swyft
        total_commission_owed = total_completed_earnings * commission_rate
        outstanding_commission = max(total_commission_owed - total_commission_paid, Decimal("0"))

        return make_response(
            jsonify(
                {
                    "driver_id": driver_id,
                    "app_orders_total": float(app_orders_total),
                    "cash_orders_total": float(cash_orders_total),
                    "total_earnings": float(total_completed_earnings),
                    "total_payments_made": float(total_commission_paid),
                    "commission": float(outstanding_commission),
                    # kept for backwards compat with any other consumers
                    "total_unpaid_earnings": float(cash_orders_total),
                    "outstanding_balance": float(cash_orders_total),
                }
            ),
            200,
            response_headers,
        )


api.add_resource(DriverEarnings, "/earnings/<driver_id>")


@app.route("/config", methods=["GET"])
def get_config():
    setting = AppSettings.query.first()
    rate = setting.commission_rate if setting else 0.18
    return jsonify({"commission_rate": rate}), 200


@app.route("/config/commission-rate", methods=["PUT"])
def update_commission_rate():
    data = request.get_json()
    new_rate = data.get("commission_rate")
    if new_rate is None or not isinstance(new_rate, (int, float)) or new_rate <= 0 or new_rate > 1:
        return jsonify({"error": "commission_rate must be a number between 0 and 1"}), 400
    setting = AppSettings.query.first()
    if setting:
        setting.commission_rate = float(new_rate)
    else:
        db.session.add(AppSettings(commission_rate=float(new_rate)))
    db.session.commit()
    return jsonify({"commission_rate": float(new_rate)}), 200


@app.route("/order-response", methods=["POST"])
@jwt_required()
def handle_order_response():
    data = request.get_json()
    order_id = data.get("order_id")
    driver_id = data.get("driver_id")
    accepted = data.get("accepted")  # True if accepted, False if declined

    order = Order.query.get(order_id)
    if not order:
        return make_response({"error": "Order not found"}, 404)

    if accepted:
        order.status = "Accepted"
        driver = Driver.query.get(order.driver_id)
        if driver:
            driver.online = 'in_transit'
        db.session.commit()

        return make_response({"message": "Order accepted"}, 200)
    else:
        # Add the current driver to the declined drivers list
        order.declined_drivers.append(driver_id)
        db.session.commit()
        db.session.refresh(order)
        print(order)
        print(driver_id)
        print(order.declined_drivers)

        # Find the next nearest driver excluding those who have declined
        drivers = Driver.query.filter(Driver.online == 'online', Driver.car_type == order.vehicle_type).all()
        nearest_driver = None
        min_distance = float("inf")
        for driver in drivers:
            if driver.id in order.declined_drivers:
                print("declined", driver.name)
                continue
            driver_distance = haversine(
                order.user_lat, order.user_lng, driver.latitude, driver.longitude
            )
            if driver_distance < min_distance:
                min_distance = driver_distance
                nearest_driver = driver

        if not nearest_driver:
            db.session.delete(order)
            db.session.commit()
            return make_response(
                {"error": "No available drivers nearby, order deleted"}, 404
            )

        print("driver", nearest_driver.name)

        order.driver_id = nearest_driver.id
        db.session.commit()

        return make_response(
            {"message": "Order declined, reassigned to next nearest driver"}, 200
        )


class ReceiveOrder(Resource):
    def post(self):
        try:
            order_data = request.get_json()
            print(f"Order data received: {order_data}")

            if not order_data:
                return make_response({"error": "No order data provided"}, 400)

            # Extract relevant details from the order_data
            order_id = order_data.get("id")
            customer_id = order_data.get("customer_id")
            vehicle_type = order_data.get("vehicle_type")
            driver_id = order_data.get("driver_id")
            total_cost = order_data.get("total_cost")
            distance = order_data.get("distance")

            # Construct a detailed success message
            message = (
                f"Incoming Order! Order ID: {order_id}, "
                f"Customer ID: {customer_id}, Vehicle Type: {vehicle_type}, "
                f"Total Cost: {total_cost}, "
                f"Distance: {distance} km."
            )

            return make_response(
                {
                    "success": True,
                    "message": message,
                    "order_id": order_id,
                    "driver_id": driver_id,
                },
                200,
            )

        except Exception as e:
            print("Not working")
            return make_response({"error": str(e)}, 500)


api.add_resource(ReceiveOrder, "/receive-order")


class ScheduleResource(Resource):
    @jwt_required()
    def get(self):
        current_user_id = get_jwt_identity()  # Get the authenticated user's ID
        schedules = ScheduledMove.query.filter_by(
            customer_id=current_user_id
        ).all()  # Fetch all schedules for the user

        if not schedules:
            return make_response({"message": "No scheduled moves found"}, 200)

        response = [
            schedule.to_dict() for schedule in schedules
        ]  # Convert to dictionary format
        return make_response(response, 200)

    @jwt_required()
    def post(self):
        data = request.get_json()
        customer_id = get_jwt_identity()

        # Extract and validate the necessary fields
        vehicle = data.get("vehicle")
        distance = data.get("distance")
        loaders = data.get("loaders")
        loader_cost = data.get("loaderCost")
        total_cost = data.get("totalCost")
        user_location = data.get("userLocation")
        destination = data.get("destination")
        time = data.get("time")
        scheduled_time = data.get("scheduledTime")  # The time for the scheduled move

        # Ensure required fields are provided
        if not all([user_location, destination, scheduled_time]):
            return make_response(
                {
                    "error": "Pickup, drop-off locations, and scheduled time are required"
                },
                400,
            )

        # Validate coordinates
        from_latitude = user_location.get("lat")
        from_longitude = user_location.get("lng")
        to_latitude = destination.get("lat")
        to_longitude = destination.get("lng")

        if not all([from_latitude, from_longitude, to_latitude, to_longitude]):
            return make_response({"error": "Invalid coordinates provided"}, 400)

        try:
            # Create and save the new schedule without assigning a driver
            new_schedule = ScheduledMove(
                customer_id=customer_id,
                vehicle_type=vehicle,
                distance=distance,
                loaders=loaders,
                loader_cost=loader_cost,
                total_cost=total_cost,
                user_lat=from_latitude,
                user_lng=from_longitude,
                dest_lat=to_latitude,
                dest_lng=to_longitude,
                time=time,
                scheduled_time=scheduled_time,
                driver_id=None,  # Driver is not assigned at this point
            )
            db.session.add(new_schedule)
            db.session.commit()

            # Return success response
            return make_response(
                {
                    "message": "Move scheduled successfully",
                    "schedule": new_schedule.to_dict(),
                },
                200,
            )
        except Exception as e:
            db.session.rollback()
            return make_response({"error": str(e)}, 500)


api.add_resource(ScheduleResource, "/schedule")


class DriverSignUp(Resource):
    def post(self):
        data = request.get_json()

        # Required fields to validate
        required_fields = {
            "tagnumber",
            "type",
            "breed",
            "sex",
            "birthdate",
            "age",
            "currentweight",
            "status",
            "penorpaddock",
            "sire",
            "dam",
            "lastvaccinationdate",
            "nextvaccinationdate",
            "averagemilk",

        }

        # Find missing fields
        missing_fields = [field for field in required_fields if not data.get(field)]
        if missing_fields:
            return make_response(
                {
                    "error": "Missing required field(s)",
                    "missing_fields": missing_fields,
                },
                400,
            )

        # Extract values
        id = data.get("id")
        username = data.get("name")
        first_name = data.get("first_name")
        last_name = data.get("last_name")
        id_number = "check_id"
        phone = data.get("phone")
        email = data.get("email")
        car_type = data.get("carType")
        password = data.get("password")
        license_plate = data.get("licensePlate")
        driving_license = data.get("driving_license")
        national_id_front = data.get("national_id_front")
        national_id_back = data.get("national_id_back")
        passport_photo = data.get("passport_photo")
        certificate_conduct = data.get("certificate_conduct")
        vehicle_picture_front = data.get("vehicle_picture_front")
        vehicle_picture_back = data.get("vehicle_picture_back")
        car_insurance = data.get("car_insurance")
        company_reg_certificate = data.get("company_reg_certificate")
        vehicle_make = data.get("vehicleMake")
        vehicle_model = data.get("vehicleModel")
        vehicle_year = data.get("vehicleYear")
        vehicle_color = data.get("vehicleColor")
        kra = data.get("kra")
        inspection_report = data.get("inspectionReport")

        # Check for existing driver
        existing_driver = Driver.query.filter(
            (Driver.email == email) | (Driver.phone == phone)
        ).first()

        if existing_driver:
            if existing_driver.email == email:
                return make_response(
                    {"error": "Email already registered, kindly login"}, 400
                )
            if existing_driver.phone == phone:
                return make_response({"error": "Phone number already registered"}, 400)

        duplicate_driver = Driver.query.filter(
            (Driver.license_plate == license_plate)
        ).first()
        if duplicate_driver:
            return make_response({"error": "Driver already registered"}, 400)

        try:
            new_driver = Driver(
                id=id,
                name=username,
                first_name=first_name,
                last_name=last_name,
                id_number=id_number,
                phone=phone,
                email=email,
                car_type=car_type,
                license_plate=license_plate,
                driving_license=driving_license,
                national_id_front=national_id_front,
                national_id_back=national_id_back,
                passport_photo=passport_photo,
                certificate_conduct=certificate_conduct,
                vehicle_picture_front=vehicle_picture_front,
                vehicle_picture_back=vehicle_picture_back,
                car_insurance=car_insurance,
                company_reg_certificate=company_reg_certificate,
                vehicle_make=vehicle_make,
                vehicle_model=vehicle_model,
                vehicle_year=vehicle_year,
                vehicle_color=vehicle_color,
                kra=kra,
                inspection_report=inspection_report,
            )

            new_driver.password_hash = password

            db.session.add(new_driver)

            # Also create a Vehicle row for this driver so the vehicles table
            # stays populated. Guarded so a vehicle problem never blocks signup:
            # plate_no is UNIQUE + NOT NULL, and licensePlate is not a required
            # field, so only insert when we have a plate that isn't already used.
            try:
                if license_plate:
                    existing_vehicle = Vehicle.query.filter_by(
                        plate_no=license_plate
                    ).first()
                    if not existing_vehicle:
                        vehicle_id = str(uuid.uuid4())
                        while Vehicle.query.filter_by(id=vehicle_id).first():
                            vehicle_id = str(uuid.uuid4())
                        new_vehicle = Vehicle(
                            id=vehicle_id,
                            body_type=car_type,
                            plate_no=license_plate,
                            driver_id=new_driver.id,
                        )
                        db.session.add(new_vehicle)
            except Exception as vehicle_error:
                # Don't let a vehicle issue break driver registration.
                print(f"Failed to create vehicle for driver: {vehicle_error}")

            db.session.commit()

            # unique_driver_id = str(uuid.uuid4())
            # while Driver.query.filter_by(id=unique_driver_id).first():
            #     unique_driver_id = str(uuid.uuid4())

            access_token = create_access_token(identity=new_driver.id)
            refresh_token = create_refresh_token(identity=new_driver.id)

            return make_response(
                {
                    "message": "Driver created successfully",
                    "user": new_driver.to_dict(),
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                },
                201,
            )

        except IntegrityError as e:
            db.session.rollback()
            return make_response({"error": "Database error: " + str(e.orig)}, 500)
        except Exception as e:
            db.session.rollback()
            return make_response({"error": "Unexpected error: " + str(e)}, 500)


api.add_resource(DriverSignUp, "/driver/signup")


@app.route("/driver/<driver_id>", methods=["GET"])
@jwt_required()
def get_driver(driver_id):
    driver = Driver.query.get(driver_id)
    if not driver:
        return make_response({"error": "Driver not found"}, 404)
    return make_response(driver.to_dict(), 200)


@app.route("/customer/<customer_id>", methods=["GET"])
@jwt_required()
def get_customer(customer_id):
    customer = Customer.query.get(customer_id)
    if not customer:
        return make_response({"error": "Customer not found"}, 404)
    return make_response(customer.to_dict(), 200)


class UpdateDriverLocation(Resource):
    def put(self, driver_id):
        data = request.get_json()
        online = data.get("online")

        location = data.get("location")
        if online and location is None:
            return make_response({"error": "Location is required"}, 400)

        driver = Driver.query.get(driver_id)
        if not driver:
            return make_response({"error": "Driver not found"}, 404)

        if not online:
            driver.online = 'offline'
            message = "You are now offline"
        else:
            if driver.online != 'in_transit':
                driver.online = 'online'
            driver.latitude = location.get("latitude")
            driver.longitude = location.get("longitude")
            message = "You are now online"

        db.session.commit()
        return make_response({"message": message, "online_status": driver.online}, 200)


api.add_resource(UpdateDriverLocation, "/online/<string:driver_id>")


@app.route("/driver/heartbeat", methods=["POST"])
@jwt_required()
def driver_heartbeat():
    driver_id = get_jwt_identity()
    data = request.get_json(force=True) or {}
    latitude = data.get("latitude")
    longitude = data.get("longitude")

    if latitude is None or longitude is None:
        return make_response({"error": "latitude and longitude are required"}, 400)

    driver = Driver.query.get(driver_id)
    if not driver:
        return make_response({"error": "Driver not found"}, 404)

    driver.latitude = float(latitude)
    driver.longitude = float(longitude)
    driver.last_heartbeat = datetime.utcnow()
    db.session.commit()

    return make_response({"ok": True}, 200)


@app.route("/driver/<driver_id>/location", methods=["GET"])
@jwt_required()
def get_driver_location(driver_id):
    driver = Driver.query.get(driver_id)
    if not driver:
        return make_response({"error": "Driver not found"}, 404)
    return make_response({
        "driver_id": driver_id,
        "latitude": driver.latitude,
        "longitude": driver.longitude,
        "online": driver.online,
        "last_updated": driver.last_heartbeat.isoformat() if driver.last_heartbeat else None,
    }, 200)


@app.route("/driver/<driver_id>/ratings", methods=["GET"])
@jwt_required()
def get_driver_ratings(driver_id):
    driver = Driver.query.get(driver_id)
    if not driver:
        return make_response({"error": "Driver not found"}, 404)

    ratings = Rating.query.filter(
        Rating.order_id.in_(
            db.session.query(Order.id).filter_by(driver_id=driver_id)
        )
    ).all()

    count = len(ratings)
    average = round(driver.rating, 2) if driver.rating else 0.0
    breakdown = {i: sum(1 for r in ratings if r.rating_score == i) for i in range(1, 6)}

    return make_response({"average": average, "count": count, "breakdown": breakdown}, 200)


@app.route("/rating/driver/<string:driver_id>", methods=["POST"])
@jwt_required()
def rate_driver(driver_id):
    import traceback
    try:
        data = request.get_json(force=True) or {}
        print(f"[RATING] payload={data}  driver_id='{driver_id}'")

        rating_score = data.get("rating") or data.get("rating_score")
        order_id = data.get("order_id")
        comment = data.get("comment") or None

        # Accept numeric strings from the client just in case
        if rating_score is not None and not isinstance(rating_score, int):
            try:
                rating_score = int(rating_score)
            except (TypeError, ValueError):
                rating_score = None

        if not rating_score or not (1 <= rating_score <= 5):
            print(f"[RATING] rejected: invalid rating_score={rating_score!r}")
            return make_response({"error": "rating must be an integer between 1 and 5"}, 400)

        driver = Driver.query.get(driver_id)
        if not driver:
            print(f"[RATING] driver '{driver_id}' not in DB — rating will be saved without driver avg update")

        # Verify order_id exists — silently drop it if it doesn't (avoids FK violation)
        if order_id:
            exists = db.session.query(Order.id).filter_by(id=order_id).scalar()
            if not exists:
                print(f"[RATING] order_id '{order_id}' not found — saving without FK")
                order_id = None

        new_rating = Rating(
            id=str(uuid.uuid4()),
            rating_score=rating_score,
            comment=comment,
            order_id=order_id,
        )
        db.session.add(new_rating)

        # Update driver average only if the driver exists
        if driver:
            existing_scores = [
                r.rating_score for r in Rating.query.filter(Rating.order_id.in_(
                    db.session.query(Order.id).filter_by(driver_id=driver_id)
                )).all()
            ]
            existing_scores.append(rating_score)
            driver.rating = round(sum(existing_scores) / len(existing_scores), 2)

        db.session.commit()
        print(f"[RATING] saved id='{new_rating.id}'  score={rating_score}  order_id='{order_id}'  driver_avg={driver.rating if driver else 'n/a'}")
        return make_response({"message": "Rating saved", "rating": new_rating.id}, 201)

    except Exception as e:
        db.session.rollback()
        print(f"[RATING] EXCEPTION: {e}")
        print(traceback.format_exc())
        return make_response({"error": str(e)}, 500)


def _verify_cron_secret():
    """Reject requests that don't carry the Vercel cron secret."""
    secret = os.environ.get("CRON_SECRET")
    if secret and request.headers.get("Authorization") != f"Bearer {secret}":
        return False
    return True


@app.route("/cron/check-inactive-drivers", methods=["GET"])
def cron_check_inactive_drivers():
    if not _verify_cron_secret():
        return make_response({"error": "Unauthorized"}, 401)
    cutoff = datetime.utcnow() - timedelta(minutes=10)
    stale = Driver.query.filter(
        Driver.online.in_(['online', 'in_transit']),
        Driver.last_heartbeat.isnot(None),
        Driver.last_heartbeat < cutoff,
    ).all()
    count = len(stale)
    for driver in stale:
        driver.online = 'offline'
    if stale:
        db.session.commit()
    print(f"[CRON] check-inactive-drivers: marked {count} driver(s) offline")
    return make_response({"ok": True, "marked_offline": count}, 200)


@app.route("/cron/check-pending-orders", methods=["GET"])
def cron_check_pending_orders():
    if not _verify_cron_secret():
        return make_response({"error": "Unauthorized"}, 401)
    check_pending_orders()
    return make_response({"ok": True}, 200)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)