require("dotenv").config();
const express = require("express");
const axios = require("axios");

const app = express();
const PORT = process.env.PORT || 3000;
const TOKEN = process.env.LINE_ACCESS_TOKEN;


const LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply";
const LINE_PUSH_URL  = "https://api.line.me/v2/bot/message/push";
const RASA_URL       = "http://localhost:5005/webhooks/rest/webhook";

function lineHeaders() {
  return {
    Authorization: `Bearer ${TOKEN}`,
    "Content-Type": "application/json",
  };
}

const sleep = (ms) => new Promise((res) => setTimeout(res, ms)); //ใช้หน่วงเวลาระหว่างข้อความ

//แยก messages ออกจาก Rasa 
function parseRasaReplies(replies) { // แปลง json จาก RASA มาให้อยู่ในรูปแบบ line
  const messages = [];
  let quickReply = null;
  for (const msg of replies) {
    //Quick Reply เก็บไว้ค่อยแนบกับข้อความ text ตัวสุดท้าย
    if (msg.custom && msg.custom.line_quick_reply) {
      quickReply = msg.custom.line_quick_reply;
      continue;
    }
    //Flex
    if (msg.custom && msg.custom.line_flex) {
      messages.push({
        type: "flex",
        altText: msg.custom.line_flex.altText || "แหล่งการเรียนรู้เพิ่มเติม",
        contents: msg.custom.line_flex.contents,
      });
      continue;
    }
    //Text
    if (msg.text) {
      messages.push({ type: "text", text: msg.text });
      continue;
    }
  }
  return { messages, quickReply };
}

//ติด Quick Reply ให้ ข้อความ text ตัวสุดท้าย
function attachQuickReplyToLastText(messages, quickReply) {
  if (!quickReply) return messages;
  //หา text message ตัวสุดท้าย
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].type === "text") {
      messages[i].quickReply = {
        items: (quickReply.items || []).slice(0, 13).map((it) => ({
          type: "action",
          action: { type: "message", label: it.label, text: it.text },
        })),
      };
      if (quickReply.text) {
        messages[i].text = quickReply.text; 
      }
      return messages;
    }
  }
  
  // ถ้าไม่มี text เพิ่ม text ใหม่ที่แนบ quick reply
  messages.push({
    type: "text",
    text: quickReply.text || "เลือกหัวข้อที่สนใจต่อได้เลยครับ",
    quickReply: {
      items: (quickReply.items || []).slice(0, 13).map((it) => ({
        type: "action",
        action: { type: "message", label: it.label, text: it.text },
      })),
    },
  });
  return messages;
}

// ส่งข้อความแรกสุดด้วย reply เพราะต้องใช้ replyToken line ต้องใช้
async function sendReply(replyToken, message) {
  await axios.post(
    LINE_REPLY_URL,
    { replyToken, messages: [message] },
    { headers: lineHeaders() }
  );
}

// ทยอยส่งที่เหลือ ด้วย push + delay ทีละข้อความ
async function sendPushProgressively(userId, messages, baseDelay, stepDelay) {
  //ข้อความต่อการส่งครั้งละ 1 ข้อความ เพื่อควบคุมจังหวะ
  for (let i = 0; i < messages.length; i++) {
    const delay = baseDelay + i * stepDelay;
    await sleep(delay);
    try {
      await axios.post(
        LINE_PUSH_URL,
        { to: userId, messages: [messages[i]] },
        { headers: lineHeaders() }
      );
    } catch (err) {
      console.error("push failed:", err.response?.data || err.message);
      // ถ้า push ล้มเหลว จะไม่หยุดทั้ง flow แค่ log ไว้
    }
  }
}

app.use(express.json());
app.use((req, res, next) => {
  console.log(`${new Date().toISOString()} → ${req.method} ${req.path}`);
  next();
});

// Routes
app.get("/", (req, res) => {
  res.send("LINE x RASA chatbot server is running");
});

app.post("/webhook", async (req, res) => {
  res.status(200).end();  //ต้องตอบ 200 ไปก่อน 
  const events = req.body.events || [];
  if (!events.length) return; 
  for (const event of events) {
    if (event.type === "message" && event.message.type === "text") {
      const userMsg    = event.message.text; //ข้อความจากผู้ใช้ 
      const replyToken = event.replyToken;   //ใช้ตอบครั้งแรก
      const userId     = event.source.userId; //ใช้ push ข้อความหลังจากข้อความแรก
      try {
        //ส่งไป Rasa
        const { data: replies } = await axios.post(RASA_URL, {
          sender: userId,
          message: userMsg,
        });
        console.log("Raw Rasa replies:", JSON.stringify(replies, null, 2));

        //แยกข้อความ + quickReply
        let { messages, quickReply } = parseRasaReplies(replies);
        if (messages.length === 0 && !quickReply) {
          //กันกรณี Rasa ไม่ตอบอะไรเลย
          messages = [
            { type: "text", text: "ขออภัยครับ ผมอาจยังไม่เข้าใจคำถาม พิมพ์ 'เมนู' เพื่อเริ่มใหม่ได้เลยครับ" },
          ];
        }

        //แนบ quickReply ให้กับข้อความสุดท้าย
        messages = attachQuickReplyToLastText(messages, quickReply);

        //ส่งข้อความแรกด้วย reply 
        const [first, ...rest] = messages;
        if (first) {
          await sendReply(replyToken, first);
        }
        if (rest.length > 0) {
          // ปรับ baseDelay/stepDelay 
          sendPushProgressively(userId, rest, 800, 900);
        } 
      } catch (err) {
        console.error("Error in webhook", err.response?.data || err.message);
        // ส่งข้อความ fallback
        try {
          await axios.post(
            LINE_REPLY_URL,
            {
              replyToken,
              messages: [
                { type: "text", text: "ระบบขัดข้องชั่วคราวครับ  ลองพิมพ์ใหม่อีกครั้งได้เลยครับ" },
              ],
            },
            { headers: lineHeaders() }
          );
        } catch (e2) {
          console.error("Fallback reply also failed:", e2.response?.data || e2.message);
        }
      }
    }
  }
});

//Start Server
app.listen(PORT, () => {
  console.log(`Server running at: http://localhost:${PORT}`);
});