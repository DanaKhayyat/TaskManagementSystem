const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const fetch = require('node-fetch');
const express = require('express');
const bodyParser = require('body-parser');

// --- إعدادات أساسية ---
const SERVER_URL = 'http://127.0.0.1:5001/submit_booking'; 
const OWNER_ID = '05xxxxxxxx'; //phone numper

// --- 1. إعداد سيرفر  (لاستقبال أوامر الإرسال من لوحة التحكم) ---
const appExpress = express();
appExpress.use(bodyParser.json());

// مسار استقبال إشعارات القبول/الإتمام من البايثون
appExpress.post('/send-confirmation', async (req, res) => {
    const { phone, message, locationUrl } = req.body;
    try {
        const chatId = phone.includes('@c.us') ? phone : `${phone}@c.us`;
        
        // إرسال الرسالة النصية (تأكيد الحجز أو طلب التقييم)
        await client.sendMessage(chatId, message);
        
        // إرسال الموقع 
        if (locationUrl) {
            await client.sendMessage(chatId, `📍 موقعنا على الخريطة:\n${locationUrl}`);
        }
        
        console.log(`✅ تم إرسال إشعار بنجاح للرقم: ${chatId}`);
        res.status(200).json({ success: true });
    } catch (error) {
        console.error('❌ فشل في إرسال الإشعار من البوت:', error);
        res.status(500).json({ success: false });
    }
});

appExpress.listen(3000, () => {
    console.log('✅ سيرفر إشعارات البوت يعمل على المنفذ 3000');
});

// --- 2. إعدادات بوت الواتساب ---
const client = new Client({
    authStrategy: new LocalAuth(),
    puppeteer: { 
        headless: true, 
        args: ['--no-sandbox', '--disable-setuid-sandbox'] 
    }
});

const sessions = new Map();

const SERVICES = {
    '1': { id: 1, name: 'جل مانيكير', price: 100 },
    '2': { id: 2, name: 'تركيب أظافر أكريليك', price: 180 },
    '3': { id: 3, name: 'رسم على الأظافر', price: 50 },
    '4': { id: 4, name: 'فرنش مانيكير', price: 110 },
    '5': { id: 5, name: 'أظافر كروم', price: 140 },
    '6': { id: 6, name: 'إصلاح وتقوية الأظافر', price: 30 },
    '7': { id: 7, name: 'تصاميم مخصصة', price: 200 }
};

function formatTo12hr(time24) {
    if (!time24.includes(':')) return time24;
    let [hours, minutes] = time24.split(':');
    hours = parseInt(hours);
    const ampm = hours >= 12 ? 'مساءً' : 'صباحاً';
    hours = hours % 12 || 12; 
    return `${hours}:${minutes} ${ampm}`;
}

function isWithinWorkingHours(time24) {
    const hours = parseInt(time24.split(':')[0]);
    return hours >= 12 && hours < 21;
}

let bootTime = Math.floor(Date.now() / 1000);

client.on('qr', qr => {
    console.log('يرجى مسح رمز الـ QR لتشغيل البوت:');
    qrcode.generate(qr, { small: true });
});

client.on('ready', () => {
    bootTime = Math.floor(Date.now() / 1000);
    console.log('✅ تم تشغيل بوت Nail Art بنجاح! يتم الآن استقبال الرسائل الجديدة.');
});
// --- 3. معالجة الرسائل الواردة (تعديل جلب الرقم الحقيقي) ---
client.on('message', async msg => {
    if (msg.timestamp < bootTime) return;
    if (msg.from.includes('@g.us')) return;

    try {
       
        let rawPhone = msg.from.split('@')[0].split(':')[0]; 

        let text = msg.body.trim();

    
        console.log(`📩 رسالة جديدة من: ${rawPhone}`);

      // --- ميزة التقييم: جلب الاسم من الواتساب وإرساله مع التقييم ---
        if (!isNaN(text) && parseInt(text) >= 1 && parseInt(text) <= 5 && !sessions.has(rawPhone)) {
            try {
                // 1. جلب بيانات جهة الاتصال لاستخراج الاسم (Pushname)
                const contact = await msg.getContact();
                const customerName = contact.pushname || "عميلة جديدة";

                const ratingData = {
                    sender_id: rawPhone,
                    receiver_id: OWNER_ID,
                   
                    messages_text: `التقييم: ${text} من 5 (بواسطة: ${customerName})`
                };

                await fetch('http://127.0.0.1:5001/save_rating', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(ratingData)
                });

                await msg.reply(`شكراً لتقييمك يا ${customerName}! نسعد دائماً بزيارتك 💅`);
                console.log(`✅ تم حفظ تقييم من: ${customerName} (${rawPhone})`);
                return; 
            } catch (e) {
                console.error('❌ خطأ في إرسال التقييم :', e.message);
            }
        }

        // --- نظام حجز المواعيد ---
        if (!sessions.has(rawPhone)) {
            if (isNaN(text)) {
                sessions.set(rawPhone, { step: 'welcome' });
            } else {
                return;
            }
        }
        // --- نظام حجز المواعيد ---
        if (!sessions.has(rawPhone)) {
            if(isNaN(text)) {
                sessions.set(rawPhone, { step: 'welcome' });
            } else {
                return;
            }
        }

        let session = sessions.get(rawPhone);

        switch (session.step) {
            case 'welcome':
                await msg.reply('أهلاً بكِ في Nail Art Studio 💅✨\n\nيسعدنا خدمتك! يرجى اختيار رقم الخدمة المطلوبة:\n1- جل مانيكير (100 ريال)\n2- تركيب أظافر أكريليك (180 ريال)\n3- رسم على الأظافر (50 ريال)\n4- فرنش مانيكير (110 ريال)\n5- أظافر كروم (140 ريال)\n6- إصلاح وتقوية الأظافر (30 ريال)\n7- تصاميم مخصصة (200 ريال)');
                session.step = 'choose_service';
                break;

            case 'choose_service':
                if (SERVICES[text]) {
                    session.service = SERVICES[text];
                    await msg.reply('يرجى كتابة الاسم الثلاثي:');
                    session.step = 'get_name';
                } else {
                    await msg.reply('عذراً، يرجى اختيار رقم من 1 إلى 7.');
                }
                break;

            case 'get_name':
                session.name = text;
                await msg.reply('يرجى إدخال رقم الجوال للتواصل:');
                session.step = 'get_phone';
                break;

            case 'get_phone':
                const phoneRegex = /^05\d{8}$/;
                if (phoneRegex.test(text)) {
                    session.customer_manual_phone = text;
                    await msg.reply('التاريخ؟ (مثال: 2026-04-25):');
                    session.step = 'get_date';
                } else {
                    await msg.reply('⚠️ عذراً، يجب إدخال رقم جوال سعودي صحيح يبدأ بـ 05.');
                }
                break;

            case 'get_date':
                session.date = text;
                await msg.reply('ساعات العمل لدينا من: 12:00 ظهراً حتى 21:00 مساءً.\nالوقت؟ (مثال: 16:30):');
                session.step = 'get_time';
                break;

            case 'get_time':
                if (isWithinWorkingHours(text)) {
                    session.time = text;
                    const displayTime = formatTo12hr(text);
                    let summary = `يرجى مراجعة بياناتك:\n👤 الاسم: ${session.name}\n📱 الجوال: ${session.customer_manual_phone}\n💅 الخدمة: ${session.service.name}\n📅 الموعد: ${session.date} في ${displayTime}\n\nأرسلي رقم (1) للتأكيد.`;
                    await msg.reply(summary);
                    session.step = 'confirm';
                } else {
                    await msg.reply('نعتذر منكِ، ساعات العمل من 12:00 ظهراً حتى 21:00 مساءً. يرجى اختيار وقت آخر.');
                }
                break;

            case 'confirm':
                if (text === '1') {
                    const params = new URLSearchParams();
                    params.append('owner_id', OWNER_ID);
                    params.append('customer_name', session.name);
                    params.append('customer_phone', session.customer_manual_phone);
                    params.append('service_id', session.service.id);
                    params.append('booking_date', session.date);
                    params.append('booking_time', session.time);
                    params.append('status', 'pending');

                    const response = await fetch(SERVER_URL, {
                        method: 'POST',
                        body: params,
                        headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
                    });

                    if (response.ok) {
                        await msg.reply('تم استلام الحجز بنجاح! 💅 سنراجع طلبك ونتواصل معك قريباً.');
                    } else {
                        await msg.reply('حدث خطأ أثناء إرسال البيانات للسيرفر.');
                    }
                    sessions.delete(rawPhone);
                }
                break;
        }
    } catch (error) {
        console.error('Bot Error:', error);
        sessions.delete(rawPhone);
    }
});

client.initialize();