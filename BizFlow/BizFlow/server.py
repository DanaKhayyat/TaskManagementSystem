from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from sqlalchemy import text
from datetime import datetime, timedelta
import requests


app = Flask(__name__)
OWNER_ID = "05xxxxxxxxxx" # phone number

app = Flask(__name__)

CORS(app, resources={r"/*": {"origins": "*"}})

# --- إعدادات قاعدة البيانات ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@127.0.0.1/business_platform'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- الجداول (Models) ---

class User(db.Model):
    __tablename__ = 'users'
    phone = db.Column(db.String(20), primary_key=True)
    username = db.Column(db.String(50))
    email = db.Column(db.String(50))
    password = db.Column(db.String(50))
    role = db.Column(db.String(20), default='admin')
    owner_id = db.Column(db.String(20), db.ForeignKey('users.phone'), nullable=True)

class Business(db.Model):
    __tablename__ = 'businesses'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    businesses_name = db.Column(db.String(100))
    description = db.Column(db.Text)
    owner_id = db.Column(db.String(20))

class Service(db.Model):
    __tablename__ = 'service'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100))
    description = db.Column(db.Text)
    price = db.Column(db.Numeric(10, 2))
    duration = db.Column(db.String(50))
    id_owner = db.Column(db.String(20))

class Booking(db.Model):
    __tablename__ = 'bookings'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    status = db.Column(db.String(20), default='pending')
    booking_date = db.Column(db.String(50))
    booking_time = db.Column(db.String(50))
    customer_id = db.Column(db.String(20)) 
    customer_name = db.Column(db.String(100)) 
    owner_id = db.Column(db.String(20))
    service_id = db.Column(db.Integer)
    staff_id = db.Column(db.String(20), nullable=True)


class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    messages_text = db.Column(db.Text)
    sender_id = db.Column(db.String(100)) 
    receiver_id = db.Column(db.String(20))
    sent_at = db.Column(db.DateTime, default=datetime.now)

# 📊 مسار الإحصائيات الجديد (نظام الأسهم)
# ==========================================

@app.route('/api/weekly_stats', methods=['GET'])
def get_weekly_stats():
    phone = request.args.get('phone')
    week_offset = int(request.args.get('offset', 0))
    
    today = datetime.now()
    start_of_week = today - timedelta(days=today.weekday() + (7 * week_offset))
    end_of_week = start_of_week + timedelta(days=6)
    
    days_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    weekly_data = []

    try:
        # 1. جلب البيانات اليومية للرسم البياني
        for i in range(7):
            current_date = (start_of_week + timedelta(days=i)).strftime('%Y-%m-%d')
            query = text("""
                SELECT 
                    SUM(s.price) as income,
                    COUNT(b.id) as total,
                    SUM(CASE WHEN b.status = 'completed' THEN 1 ELSE 0 END) as sales,
                    SUM(CASE WHEN b.status = 'cancelled' THEN 1 ELSE 0 END) as cancels
                FROM bookings b
                LEFT JOIN service s ON b.service_id = s.id
                WHERE b.owner_id = :phone AND b.booking_date = :bdate
            """)
            res = db.session.execute(query, {'phone': phone, 'bdate': current_date}).fetchone()
            
            income = float(res.income or 0)
            weekly_data.append({
                "day": days_names[i],
                "date": (start_of_week + timedelta(days=i)).strftime('%d %b'),
                "income": income,
                "sales": int(res.sales or 0),
                "cancels": int(res.cancels or 0),
                "total": int(res.total or 0)
            })

        # 2. استعلام الخدمات الأكثر طلباً خلال هذا الأسبوع
        top_services_query = text("""
            SELECT s.name, COUNT(b.id) as count
            FROM bookings b
            JOIN service s ON b.service_id = s.id
            WHERE b.owner_id = :phone 
            AND b.booking_date BETWEEN :start AND :end
            GROUP BY s.name
            ORDER BY count DESC
            LIMIT 3
        """)
        top_res = db.session.execute(top_services_query, {
            'phone': phone, 
            'start': start_of_week.strftime('%Y-%m-%d'), 
            'end': end_of_week.strftime('%Y-%m-%d')
        }).fetchall()
        
        top_services = [{"name": r.name, "count": r.count} for r in top_res]

        return jsonify({
            "success": True,
            "range": f"{start_of_week.strftime('%d %b')} - {end_of_week.strftime('%d %b')}",
            "data": weekly_data,
            "top_services": top_services
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ==========================================
# 📱 مسارات تطبيق الجوال (Mobile API)
# ==========================================


@app.route('/api/add_staff', methods=['POST', 'OPTIONS'])
def add_staff():
    """دالة إضافة موظف جديد من قبل المدير مع الربط الصحيح بالمدير"""
    if request.method == 'OPTIONS': return jsonify({"success": True}), 200
    data = request.get_json()
    phone = data.get('phone')
    
    # استلام رقم جوال المدير (صاحب الحساب الحالي) لربطه بالموظف في خانة owner_id
    manager_phone = data.get('manager_phone') 
    
    # التأكد من عدم تكرار رقم جوال الموظف في النظام
    if User.query.filter_by(phone=phone).first():
        return jsonify({"success": False, "message": "رقم الجوال مسجل مسبقاً"}), 400
    
    try:
        new_staff = User(
            phone=phone,
            username=data.get('name'),
            password=data.get('password'),
            role='staff', 
            owner_id=manager_phone, 
            email=f"staff_{phone}@bizflow.com" 
        )
        db.session.add(new_staff)
        db.session.commit()
        return jsonify({"success": True, "message": "تمت إضافة الموظف بنجاح"}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/signup_mobile', methods=['POST', 'OPTIONS'])
def signup_mobile_api():
    if request.method == 'OPTIONS': return jsonify({"success": True}), 200
    data = request.get_json()
    phone = data.get('phone')
    if User.query.filter_by(phone=phone).first():
        return jsonify({"success": False, "message": "رقم الجوال مسجل مسبقاً"}), 400
    try:
        new_user = User(
            phone=phone, 
            username=data.get('username'), 
            email=data.get('email'), 
            password=data.get('password'),
            role='admin'
        )
        db.session.add(new_user)
        db.session.commit()
        return jsonify({"success": True, "message": "تم إنشاء الحساب بنجاح"}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/login', methods=['POST', 'OPTIONS'])
def login_api():
    if request.method == 'OPTIONS': return jsonify({"success": True}), 200
    data = request.get_json()
    user = User.query.filter_by(phone=data.get('phone'), password=data.get('password')).first()
    if user: 
        return jsonify({
            "success": True, 
            "username": user.username, 
            "phone": user.phone,
            "role": getattr(user, 'role', 'admin') 
        }), 200
    return jsonify({"success": False}), 401

@app.route('/api/create_business', methods=['POST', 'OPTIONS'])
def create_business_api():
    if request.method == 'OPTIONS': return jsonify({"success": True}), 200
    data = request.get_json()
    phone = data.get('phone')
    try:
        biz = Business.query.filter_by(owner_id=phone).first()
        if not biz:
            biz = Business(owner_id=phone)
            db.session.add(biz)
        biz.businesses_name = data.get('businessName')
        biz.description = data.get('businessDescription')
        db.session.commit()
        return jsonify({"success": True, "message": "تم حفظ بيانات النشاط"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/add_service', methods=['POST', 'OPTIONS'])
def add_service():
    if request.method == 'OPTIONS': return jsonify({"success": True}), 200
    data = request.get_json()
    try:
        new_service = Service(
            name=data.get('name'),
            price=data.get('price'),
            id_owner=data.get('phone'),
            description=data.get('description') if data.get('description') else "",
            duration=data.get('duration') if data.get('duration') else ""
        )
        db.session.add(new_service)
        db.session.commit()
        return jsonify({"success": True}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False}), 500
    

@app.route('/api/get_business', methods=['GET'])
@app.route('/api/get_business', methods=['GET'])
def get_business_api():
    phone = request.args.get('phone')
    user = User.query.filter_by(phone=phone).first()
    
    if not user: 
        return jsonify({"success": False, "message": "المستخدم غير موجود"}), 404

    
    target_phone = user.owner_id if user.role == 'staff' and user.owner_id else user.phone
    
    # جلب بيانات البزنس بناءً على رقم المدير 
    biz = Business.query.filter_by(owner_id=target_phone).first()
    
    services_list = []
    try:
        # جلب الخدمات التابعة للمدير المسؤول
        services = Service.query.filter_by(id_owner=target_phone).all()
        for s in services:
            services_list.append({
                "id": s.id, 
                "name": s.name, 
                "description": s.description if s.description else "", 
                "price": str(s.price), 
                "duration": s.duration if s.duration else ""
            })
    except Exception as e: 
        print(f"Error fetching services: {e}")

    return jsonify({
        "success": True, 
        "username": user.username, 
        "email": user.email, 
        "phone": user.phone,
        "role": getattr(user, 'role', 'admin'),
        "businessName": biz.businesses_name if biz else "لم يحدد اسم", 
        "businessDescription": biz.description if biz else "لا يوجد وصف حالياً",
        "services": services_list 
    }), 200
@app.route('/api/get_bookings', methods=['GET'])
def get_bookings():
    phone = request.args.get('phone')
    try:
        user = User.query.filter_by(phone=phone).first()
        if not user:
            return jsonify({"success": False, "message": "المستخدم غير موجود"}), 404
            
        # تحديد رقم المدير المسؤول عن الحجوزات
        target_phone = user.owner_id if user.role == 'staff' else phone
        
        # استعلام مطور يجلب بيانات الحجز مع ضمان جلب الوقت والتاريخ
        query = text("""
            SELECT 
                b.id, b.customer_id, b.customer_name, b.booking_date, b.booking_time, b.status, 
                s.name as service_name, 
                u.username as employee_name
            FROM bookings b 
            LEFT JOIN service s ON b.service_id = s.id 
            LEFT JOIN users u ON b.staff_id = u.phone
            WHERE b.owner_id = :target 
            ORDER BY b.id DESC
        """)
        
        bookings = db.session.execute(query, {'target': target_phone}).fetchall()
        
        results = []
        for b in bookings:
            results.append({
                "id": b.id, 
                "customer_phone": b.customer_id, 
                "customer_name": b.customer_name if b.customer_name else "بدون اسم",
                "date": str(b.booking_date) if b.booking_date else "0000-00-00", 
                "booking_time": str(b.booking_time) if b.booking_time else "غير محدد", 
                "status": b.status, 
                "serviceName": b.service_name if b.service_name else "خدمة غير محددة",
                "employee_name": b.employee_name if b.employee_name else "المدير"
            })
            
        return jsonify({"success": True, "bookings": results}), 200
    except Exception as e: 
        return jsonify({"success": False, "message": str(e)}), 500
# --- 2. مسار تحديث حالة الحجز وإرسال إشعارات الواتساب () ---
@app.route('/api/update_booking_status', methods=['POST', 'OPTIONS'])
def update_booking_status():
    if request.method == 'OPTIONS': return jsonify({"success": True}), 200
    data = request.get_json()
    booking_id = data.get('booking_id')
    new_status = data.get('status')
    emp_phone = data.get('staff_id') 
    
    try:
        # استخدام db.session.get بدلاً من query.get لتجنب التنبيهات
        booking = db.session.get(Booking, booking_id)
        if booking:
            booking.status = new_status
            
            # إذا اكتملت الخدمة، نسجل الموظف المسؤول
            if new_status == 'completed':
                booking.staff_id = emp_phone
            
            db.session.commit()

            # --- إرسال الإشعار لبوت الواتساب (Node.js) ---
            try:
                bot_url = "http://127.0.0.1:3000/send-confirmation"
                
                # تجهيز الرقم (تحويله للصيغة الدولية 966)
                customer_phone = str(booking.customer_id).strip()
                if customer_phone.startswith('05'):
                    customer_phone = '966' + customer_phone[1:]
                elif customer_phone.startswith('5'):
                    customer_phone = '966' + customer_phone

                payload = None
                
                # الحالة 1: قبول الحجز (إرسال رسالة ترحيب ولوكيشن)
                if new_status in ['urgent', 'confirmed']:
                    payload = {
                        "phone": customer_phone,
                        "message": f"تم قبول حجزك بنجاح يا {booking.customer_name}! نحن بانتظارك. ✨💅",
                        "locationUrl": "https://maps.app.goo.gl/yifBQh8oXGYRt5Pv7"
                    }

                # الحالة 2: إتمام الخدمة (إرسال طلب التقييم)
                elif new_status == 'completed':
                    payload = {
                        "phone": customer_phone,
                        "message": "🌸 شكراً لزيارتك لـ Nail Art Studio! يسعدنا تقييمك للخدمة من 1 إلى 5 عبر الرد على هذه الرسالة برقم فقط."
                    }

                if payload:
                    response = requests.post(bot_url, json=payload, timeout=5)
                    print(f"✅ تم إرسال الطلب للبوت بنجاح للرقم {customer_phone}, استجابة البوت: {response.status_code}")
                    
            except Exception as bot_err:
                print(f"⚠️ فشل في التواصل مع البوت (تأكدي أن node app.js يعمل): {bot_err}")

            return jsonify({"success": True}), 200
        return jsonify({"success": False, "message": "الحجز غير موجود"}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

# --- 3. مسار تحديث بيانات النشاط التجاري ---
@app.route('/api/update_business', methods=['POST', 'OPTIONS'])
def update_business():
    if request.method == 'OPTIONS': return jsonify({"success": True}), 200
    data = request.get_json()
    phone = data.get('phone')
    
    try:
        biz = Business.query.filter_by(owner_id=phone).first()
        if not biz:
            biz = Business(owner_id=phone)
            db.session.add(biz)
            
        biz.businesses_name = data.get('businessName')
        biz.description = data.get('businessDescription')
        
        db.session.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

# --- 4. مسار استقبال وحفظ التقييمات القادمة من البوت ---
@app.route('/save_rating', methods=['POST'])
def save_rating():
    try:
        # 1. جلب البيانات من الطلب (يدعم صيغتين: Form Data و JSON)
        data = request.get_json() if request.is_json else request.form
        sender_id = data.get('sender_id')
        receiver_id = data.get('receiver_id')
        msg_text = data.get('messages_text')

        print(f"📥 محاولة حفظ تقييم واردة من الرقم: {sender_id}")

        # 2. التحقق من اكتمال البيانات الأساسية
        if not sender_id or not msg_text:
            print("⚠️ تم تجاهل الطلب: البيانات المرسلة من البوت ناقصة.")
            return "Missing Data", 400

       
        clean_sender = sender_id.split('@')[0] if '@' in sender_id else sender_id

        # 4. إعداد استعلام SQL 
        query = text("""
            INSERT INTO messages (messages_text, sender_id, receiver_id, sent_at)
            VALUES (:text, :sender, :receiver, NOW())
        """)
        
        # 5. تنفيذ العملية مع ربط المتغيرات
        db.session.execute(query, {
            'text': msg_text,
            'sender': clean_sender, 
            'receiver': receiver_id if receiver_id else "05xxxxxxxxxx" # phone number
        })
        
      
        db.session.commit()
        
        print(f"⭐️ نجح الحفظ! الرقم المنظف: {clean_sender} | نص التقييم: {msg_text}")
        return "Rating Saved", 200

    except Exception as e:
        # التراجع في حال حدوث خطأ
        db.session.rollback()
        print(f"❌ خطأ تقني أثناء محاولة الحفظ: {str(e)}")
        return "Error", 500
    
    # --- مسار جلب التقييمات (باستخدام OWNER_ID المعرف في الأعلى) ---
@app.route('/api/get_my_ratings', methods=['GET'])
def get_my_ratings():
    try:
        # نستخدم OWNER_ID بدلاً من كتابة الرقم هنا
        query = text("""
            SELECT messages_text, sender_id, sent_at 
            FROM messages 
            WHERE receiver_id = :owner 
            ORDER BY sent_at DESC
        """)
        
        # نربط المتغير المعرف فوق بالاستعلام
        result = db.session.execute(query, {'owner': OWNER_ID}).fetchall()
        
        ratings_list = []
        for row in result:
            ratings_list.append({
                'text': row[0],
                'sender': row[1],
                'date': row[2].strftime("%Y-%m-%d %H:%M")
            })
            
        return jsonify({
            "success": True, 
            "ratings": ratings_list,
            "count": len(ratings_list)
        }), 200

    except Exception as e:
        print(f"❌ خطأ في جلب التقييمات: {str(e)}")
        return jsonify({"success": False, "message": "حدث خطأ أثناء تحميل التقييمات"}), 500
# ==========================================
# 🌐 مسارات الموقع (Web)
# ==========================================

@app.route('/')
def landing(): return render_template('landing.html')

@app.route('/register')
def register_web(): return render_template('index.html')

@app.route('/save_user', methods=['POST'])
def save_user_web():
    try:
        phone = request.form.get('u_phone')
        new_user = User(
            phone=phone, 
            username=request.form.get('u_name'), 
            email=request.form.get('u_email'), 
            password=request.form.get('u_pass'),
            role='admin'
        )
        db.session.add(new_user)
        db.session.commit()
        return render_template('business_web.html', phone=phone)
    except: 
        db.session.rollback()
        return "خطأ في حفظ بيانات المستخدم"

@app.route('/save_business_data', methods=['POST'])
def save_business_web():
    try:
        new_biz = Business(businesses_name=request.form.get('business_name'), description=request.form.get('business_desc'), owner_id=request.form.get('phone'))
        db.session.add(new_biz)
        db.session.commit()
        return '<script>alert("تم حفظ البيانات، يرجى التسجيل من التطبيق للمتابعة"); window.location.href = "/";</script>'
    except: 
        db.session.rollback() 
        return "خطأ في حفظ بيانات النشاط"

@app.route('/booking')
def show_booking_page():
    owner_phone = request.args.get('owner')
    services_list = Service.query.filter_by(id_owner=owner_phone).all()
    biz = Business.query.filter_by(owner_id=owner_phone).first()
    biz_name = biz.businesses_name if biz else "نشاط تجاري"
    return render_template('booking.html', biz_name=biz_name, owner_id=owner_phone, services=services_list)

from datetime import datetime

@app.route('/submit_booking', methods=['POST'])
def submit_booking():
    try:
        # 1. جلب البيانات
        raw_date = request.form.get('booking_date') 
        raw_time = request.form.get('booking_time')
        
        # 2. التاريخ)
        clean_date = None
        if raw_date:
            try:
                # إذا كان التاريخ جاي من الفورم (YYYY-MM-DD)
                if "-" in raw_date and len(raw_date.split("-")[0]) == 4:
                    clean_date = raw_date
                # إذا كان التاريخ جاي من البوت (DD-MM-YYYY)
                elif "-" in raw_date:
                    parts = raw_date.split("-")
                    clean_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
                else:
                    clean_date = raw_date
            except:
                clean_date = raw_date

        # 3. حفظ في قاعدة البيانات
        new_booking = Booking(
            customer_name=request.form.get('customer_name'),
            customer_id=request.form.get('customer_phone'),
            booking_date=clean_date,
            booking_time=raw_time if raw_time else "00:00",
            owner_id=request.form.get('owner_id'),
            service_id=request.form.get('service_id'),
            status=request.form.get('status', 'pending')
        )

        db.session.add(new_booking)
        db.session.commit()
        
        print(f"✅ تم الحفظ! من الواتس/الفورم: {clean_date}")
        return "Success", 200

    except Exception as e:
        db.session.rollback()
        print(f"❌ خطأ: {str(e)}")
        return str(e), 500
    
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)