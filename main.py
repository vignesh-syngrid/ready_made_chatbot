import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
import os
import hashlib
import time
import json
from typing import Optional, Dict, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# Load environment variables from .env file (if exists)
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("[ENV] ✅ Environment variables loaded from .env file")
except ImportError:
    print("[ENV] ⚠️ python-dotenv not installed. Using system environment variables.")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_API_BASE = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "arcee-ai/trinity-large-preview:free"

print("\n" + "="*50)
print("CONFIGURATION CHECK")
print("="*50)
print(f"OPENROUTER_API_KEY: {'SET' if OPENROUTER_API_KEY else 'NOT SET ❌'}")
print("="*50 + "\n")

class InMemoryStorage:
    """Handles all data storage in memory - replaces MySQL database"""
    
    def __init__(self):
        self.leads = []
        self.chatbots = {}
        self.next_lead_id = 1
        self.next_chatbot_id = 1
    
    def save_lead(self, chatbot_id, company_name, user_name, user_email, 
                  user_phone, session_id, questions_asked, conversation):
        """Save lead to in-memory storage"""
        try:
            lead = {
                'userid': self.next_lead_id,
                'username': user_name or "Anonymous",
                'mailid': user_email or "not_provided@example.com",
                'phonenumber': user_phone or "Not provided",
                'conversation': json.dumps(conversation) if conversation else "[]",
                'timestart': datetime.now(),
                'timeend': None,
                'chatbot_id': chatbot_id,
                'company_name': company_name,
                'session_id': session_id,
                'questions_asked': questions_asked
            }
            
            self.leads.append(lead)
            self.next_lead_id += 1
            print(f"[Storage] Lead saved successfully with ID: {lead['userid']}")
            return True
        except Exception as e:
            print(f"[Storage]  Save lead error: {e}")
            st.error(f"Failed to save lead: {e}")
            return False
    
    def get_leads(self, chatbot_id=None):
        """Retrieve leads from in-memory storage"""
        try:
            if chatbot_id:
                return [lead for lead in self.leads if lead['chatbot_id'] == chatbot_id]
            return self.leads
        except Exception as e:
            print(f"[Storage] ❌ Get leads error: {e}")
            return []
    
    def save_chatbot(self, chatbot_id, company_name, website_url, embed_code):
        """Save or update chatbot configuration"""
        try:
            self.chatbots[chatbot_id] = {
                'id': self.next_chatbot_id,
                'chatbot_id': chatbot_id,
                'company_name': company_name,
                'website_url': website_url,
                'embed_code': embed_code,
                'created_at': datetime.now(),
                'updated_at': datetime.now()
            }
            self.next_chatbot_id += 1
            print(f"[Storage] ✅ Chatbot saved: {company_name}")
            return True
        except Exception as e:
            print(f"[Storage] ❌ Chatbot save error: {e}")
            return False
    
    def get_chatbot(self, chatbot_id):
        """Get chatbot configuration"""
        return self.chatbots.get(chatbot_id)

storage = InMemoryStorage()

# WEBSITE SCRAPER

class FastScraper:
    """Fast website scraper with multi-threading"""
    
    def __init__(self):
        self.headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        self.timeout = 6
    
    def scrape_page(self, url):
        """Scrape a single page"""
        try:
            resp = requests.get(url, headers=self.headers, timeout=self.timeout)
            if resp.status_code != 200:
                return None
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            for tag in soup(['script', 'style', 'nav', 'footer']):
                tag.decompose()
            
            content = soup.get_text(separator='\n', strip=True)
            lines = [l.strip() for l in content.split('\n') if len(l.strip()) > 25][:50]
            
            return {"url": url, "content": '\n'.join(lines)[:4000]} if lines else None
        except Exception as e:
            print(f"[Scraper] Error scraping {url}: {e}")
            return None
    
    def scrape_website(self, base_url, progress_callback=None):
        """Scrape multiple pages from a website"""
        if not base_url.startswith('http'):
            base_url = 'https://' + base_url
        
        urls = [base_url, f"{base_url}/about", f"{base_url}/services", 
                f"{base_url}/contact", f"{base_url}/products"]
        
        pages = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(self.scrape_page, url): url for url in urls}
            for i, future in enumerate(as_completed(futures)):
                if progress_callback:
                    progress_callback(i+1, len(urls), futures[future])
                result = future.result()
                if result:
                    pages.append(result)
        
        all_text = '\n'.join([p['content'] for p in pages])
        emails = list(set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', all_text)))[:3]
        phones = list(set(re.findall(r'\+?\d[\d\s.-]{7,}\d', all_text)))[:3]
        
        return pages, {"emails": emails, "phones": phones}


# AI INTEGRATION

class SmartAI:
    """AI integration with caching"""
    
    def __init__(self):
        self.cache = {}
    
    def call_llm(self, prompt):
        """Call LLM API with caching"""
        if not OPENROUTER_API_KEY:
            return "⚠️ API key not set. Please configure OPENROUTER_API_KEY."
        
        cache_key = hashlib.md5(prompt.encode()).hexdigest()[:12]
        if cache_key in self.cache:
            print("[AI] Cache hit")
            return self.cache[cache_key]
        
        try:
            resp = requests.post(
                OPENROUTER_API_BASE,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://localhost:8501",
                    "X-Title": "AI Chatbot Lead Generator"
                },
                json={
                    "model": MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 400
                },
                timeout=30
            )
            
            if resp.status_code == 200:
                data = resp.json()
                if "choices" in data:
                    answer = data["choices"][0]["message"]["content"].strip()
                    self.cache[cache_key] = answer
                    return answer
            
            # Enhanced error handling
            print(f"[AI] API Response Status: {resp.status_code}")
            print(f"[AI] API Response: {resp.text}")
            
            if resp.status_code == 401:
                return "⚠️ API Authentication Failed. Please check your OPENROUTER_API_KEY is valid and has credits."
            elif resp.status_code == 402:
                return "⚠️ Insufficient credits. Please add credits to your OpenRouter account."
            elif resp.status_code == 429:
                return "⚠️ Rate limit exceeded. Please try again in a moment."
            else:
                return f"⚠️ API Error {resp.status_code}: {resp.text[:100]}"
                
        except Exception as e:
            print(f"[AI] Error: {e}")
            return "I'm having connection issues. Please try again."

# CHATBOT CLASS
class UniversalChatbot:
    """Universal chatbot that works for any website"""
    
    def __init__(self, company_name, website_url, chatbot_id):
        self.company_name = company_name
        self.website_url = website_url
        self.chatbot_id = chatbot_id
        self.pages = []
        self.contact_info = {}
        self.ready = False
        self.ai = SmartAI()
    
    def initialize(self, progress_callback=None):
        """Initialize chatbot by scraping website"""
        try:
            scraper = FastScraper()
            self.pages, self.contact_info = scraper.scrape_website(self.website_url, progress_callback)
            self.ready = True
            print(f"[Bot] Initialized for {self.company_name}")
            return True
        except Exception as e:
            print(f"[Bot] Initialization error: {e}")
            return False
    
    def ask(self, question):
        """Process user question and generate response"""
        if not self.ready:
            return "⚠️ Chatbot not ready. Please try again."
        
        # Handle greetings
        if any(g in question.lower() for g in ['hi', 'hello', 'hey']):
            return f"👋 Hello! I'm the AI assistant for **{self.company_name}**. How can I help you today?"
        
        # Handle contact info requests
        if any(k in question.lower() for k in ['email', 'contact', 'phone']):
            msg = f"📞 **Contact {self.company_name}**\n\n"
            if self.contact_info.get('emails'):
                msg += "📧 " + ", ".join(self.contact_info['emails']) + "\n"
            if self.contact_info.get('phones'):
                msg += "📱 " + ", ".join(self.contact_info['phones']) + "\n"
            msg += f"🌐 {self.website_url}"
            return msg
        
        # Generate AI response with context
        context = '\n'.join([p['content'][:800] for p in self.pages[:3]])
        
        prompt = f"""You are a helpful assistant for {self.company_name}.

Context from their website:
{context}

User question: {question}

Provide a helpful, natural 2-3 sentence answer.

Answer:"""
        
        return self.ai.call_llm(prompt)


# UTILITY FUNCTIONS

def generate_embed_code(chatbot_id, company_name):
    """Generate HTML embed code for chatbot widget"""
    return f'''<!-- {company_name} AI Chatbot -->
<div id="chatbot-{chatbot_id}"></div>
<script>
(function(){{
  var btn=document.createElement('button');
  btn.innerHTML='💬 Chat';
  btn.style.cssText='position:fixed;bottom:20px;right:20px;background:#0066cc;color:white;border:none;border-radius:50px;padding:15px 25px;font-size:16px;cursor:pointer;box-shadow:0 4px 12px rgba(0,0,0,0.3);z-index:9999;';
  
  var iframe=document.createElement('iframe');
  iframe.src='YOUR_SERVER_URL?id={chatbot_id}';
  iframe.style.cssText='position:fixed;bottom:80px;right:20px;width:400px;height:600px;border:none;border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,0.4);z-index:9998;display:none;';
  
  btn.onclick=function(){{
    iframe.style.display=iframe.style.display==='none'?'block':'none';
  }};
  
  document.body.appendChild(btn);
  document.body.appendChild(iframe);
}})();
</script>'''

def validate_email(email):
    """Validate email format - Basic check"""
    if not email or not email.strip():
        return False
    return '@' in email and '.' in email.split('@')[-1]

def init_session():
    """Initialize session state variables"""
    defaults = {
        'chatbots': {},
        'current_company': None,
        'chat_history': [],
        'question_count': 0,
        'lead_capture_mode': None,
        'lead_data': {},
        'session_id': hashlib.md5(str(datetime.now()).encode()).hexdigest()[:16],
        'lead_captured': False
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# MAIN APPLICATION
def main():
    """Main Streamlit application"""
    st.set_page_config(page_title="AI Chatbot Lead Generator", page_icon="🤖", layout="wide")
    init_session()
    
    st.title("🤖 Universal AI Chatbot with Lead Capture")
    st.caption("Automatic lead capture after 3 questions + One-click website embed!")
    
    # Check API key
    if not OPENROUTER_API_KEY:
        st.error("⚠️ OPENROUTER_API_KEY not set!")
        st.info("Set it with:")
        st.code("export OPENROUTER_API_KEY='your_key'", language="bash")
        st.info("Or create a .env file with: OPENROUTER_API_KEY=your_key")
        
        with st.expander("🔑 How to get an OpenRouter API Key"):
            st.markdown("""
            1. Go to [OpenRouter.ai](https://openrouter.ai/)
            2. Sign up or log in
            3. Go to [Keys](https://openrouter.ai/keys)
            4. Create a new API key
            5. Add credits to your account (Settings → Credits)
            6. Copy the key and set it as OPENROUTER_API_KEY
            """)
        st.stop()
    
    # Sidebar - Management
    st.sidebar.title("🏢 Management")
    
    # API Status Check
    with st.sidebar.expander("🔑 API Key Status"):
        key_preview = f"{OPENROUTER_API_KEY[:8]}...{OPENROUTER_API_KEY[-4:]}" if len(OPENROUTER_API_KEY) > 12 else "Invalid format"
        st.success(f"✅ Key Set: {key_preview}")
        st.caption("Make sure you have credits in your OpenRouter account!")
        if st.button("🧪 Test API Connection"):
            with st.spinner("Testing..."):
                test_ai = SmartAI()
                result = test_ai.call_llm("Say 'Hello, I'm working!' in one short sentence.")
                if "⚠️" in result:
                    st.error(result)
                else:
                    st.success(f"✅ API Working: {result}")
    
    with st.sidebar.expander("➕ New Chatbot", expanded=True):
        name = st.text_input("Company Name")
        url = st.text_input("Website URL")
        
        if st.button("🚀 Create", type="primary"):
            if name and url:
                chatbot_id = hashlib.md5(f"{name}{url}{time.time()}".encode()).hexdigest()[:12]
                slug = re.sub(r'[^a-z0-9]+', '-', name.lower())
                
                progress = st.progress(0)
                status = st.empty()
                
                def cb(done, total, url_str):
                    progress.progress(done/total)
                    status.text(f"{done}/{total}: {url_str[:40]}...")
                
                bot = UniversalChatbot(name, url, chatbot_id)
                if bot.initialize(cb):
                    st.session_state.chatbots[slug] = bot
                    st.session_state.current_company = slug
                    st.session_state.chat_history = []
                    st.session_state.question_count = 0
                    st.session_state.lead_captured = False
                    st.session_state.lead_capture_mode = None
                    st.session_state.lead_data = {}
                    
                    embed = generate_embed_code(chatbot_id, name)
                    storage.save_chatbot(chatbot_id, name, url, embed)
                    st.success("✅ Ready!")
                    st.rerun()
    
    if st.session_state.chatbots:
        st.sidebar.subheader("📋 Chatbots")
        for slug, bot in st.session_state.chatbots.items():
            col1, col2 = st.sidebar.columns([3,1])
            with col1:
                if st.button(f"💬 {bot.company_name}", key=f"sel_{slug}"):
                    st.session_state.current_company = slug
                    st.session_state.chat_history = []
                    st.session_state.question_count = 0
                    st.session_state.lead_captured = False
                    st.session_state.lead_capture_mode = None
                    st.session_state.lead_data = {}
                    st.rerun()
            with col2:
                if st.button("🗑️", key=f"del_{slug}"):
                    del st.session_state.chatbots[slug]
                    if st.session_state.current_company == slug:
                        st.session_state.current_company = None
                    st.rerun()
    
    if st.sidebar.button("📊 View Leads"):
        st.subheader("📊 Captured Leads")
        st.info("ℹ️ Leads are stored in memory and will be lost when the app restarts.")
        leads = storage.get_leads()
        if leads:
            for lead in leads:
                with st.expander(f"🎯 {lead['username']} - {lead['company_name']}"):
                    st.write(f"**Email:** {lead['mailid']}")
                    st.write(f"**Phone:** {lead['phonenumber']}")
                    st.write(f"**Questions:** {lead['questions_asked']}")
                    st.write(f"**Start Time:** {lead['timestart']}")
                    if lead.get('timeend'):
                        st.write(f"**End Time:** {lead['timeend']}")
                    st.write(f"**Session ID:** {lead['session_id']}")
        else:
            st.info("No leads yet")
        return
    
    # Main Chat Interface
    if not st.session_state.current_company:
        st.info("👈 Create a chatbot to start!")
        return
    
    bot = st.session_state.chatbots[st.session_state.current_company]
    
    col1, col2, col3 = st.columns([2,1,1])
    with col1:
        st.subheader(f"💬 {bot.company_name}")
    with col2:
        st.metric("Questions", st.session_state.question_count)
    with col3:
        if st.session_state.lead_captured:
            st.success("✅ Lead")
        else:
            st.info("🎯 Pending")
    
    with st.expander("🔗 Get Embed Code", expanded=False):
        embed = generate_embed_code(bot.chatbot_id, bot.company_name)
        st.code(embed, language='html')
        st.download_button("📥 Download Widget", embed, f"{bot.company_name}_chatbot_widget.html", "text/html")
        st.info("Replace YOUR_SERVER_URL with your actual server URL")
    
    # Display chat history
    for msg in st.session_state.chat_history:
        with st.chat_message(msg['role']):
            st.markdown(msg['content'])
    
    # Lead Capture Form
    if st.session_state.lead_capture_mode and not st.session_state.lead_captured:
        st.markdown("---")
        st.markdown("### 🎯 We'd love to help you better!")
        
        if st.session_state.lead_capture_mode == 'ask_name':
            st.info("**May I know your name?**")
            name = st.text_input("Your Name", key="name_input", placeholder="e.g., John Doe")
            
            col1, col2 = st.columns([1, 3])
            with col1:
                if st.button("✅ Submit", type="primary", key="submit_name"):
                    if name and name.strip():
                        st.session_state.lead_data['name'] = name.strip()
                        st.session_state.lead_capture_mode = 'ask_email'
                        st.rerun()
                    else:
                        st.error("Please enter your name")
            with col2:
                if st.button("⏭️ Skip", key="skip_name"):
                    st.session_state.lead_data['name'] = "Anonymous"
                    st.session_state.lead_capture_mode = 'ask_email'
                    st.rerun()
        
        elif st.session_state.lead_capture_mode == 'ask_email':
            st.info("**What's your email address?**")
            email = st.text_input("Your Email", key="email_input", placeholder="e.g., john@example.com")
            
            col1, col2 = st.columns([1, 3])
            with col1:
                if st.button("✅ Submit", type="primary", key="submit_email"):
                    if email and validate_email(email):
                        st.session_state.lead_data['email'] = email.strip()
                        st.session_state.lead_capture_mode = 'ask_phone'
                        st.rerun()
                    else:
                        st.error("Please enter a valid email")
            with col2:
                if st.button("⏭️ Skip", key="skip_email"):
                    st.session_state.lead_data['email'] = "not_provided@example.com"
                    st.session_state.lead_capture_mode = 'ask_phone'
                    st.rerun()
        
        elif st.session_state.lead_capture_mode == 'ask_phone':
            st.info("**And your phone number?**")
            st.caption("Any format accepted - enter your number")
            phone = st.text_input("Your Phone", key="phone_input", 
                                placeholder="e.g., +1234567890, 123-456-7890, or any format")
            
            col1, col2 = st.columns([1, 3])
            with col1:
                if st.button("✅ Submit", type="primary", key="submit_phone"):
                    phone_value = phone.strip() if phone else "Not provided"
                    st.session_state.lead_data['phone'] = phone_value
                    
                    with st.spinner("Saving..."):
                        success = storage.save_lead(
                            bot.chatbot_id,
                            bot.company_name,
                            st.session_state.lead_data.get('name', 'Anonymous'),
                            st.session_state.lead_data.get('email', 'not_provided@example.com'),
                            st.session_state.lead_data.get('phone', 'Not provided'),
                            st.session_state.session_id,
                            st.session_state.question_count,
                            st.session_state.chat_history
                        )
                    
                    if success:
                        st.session_state.lead_captured = True
                        st.session_state.lead_capture_mode = None
                        st.balloons()
                        st.success("✅ Thank you! Continuing chat...")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("Storage save failed. Check console for details.")
            
            with col2:
                if st.button("⏭️ Skip", key="skip_phone"):
                    with st.spinner("Saving..."):
                        success = storage.save_lead(
                            bot.chatbot_id,
                            bot.company_name,
                            st.session_state.lead_data.get('name', 'Anonymous'),
                            st.session_state.lead_data.get('email', 'not_provided@example.com'),
                            "Not provided",
                            st.session_state.session_id,
                            st.session_state.question_count,
                            st.session_state.chat_history
                        )
                    
                    if success:
                        st.session_state.lead_captured = True
                        st.session_state.lead_capture_mode = None
                        st.balloons()
                        st.success("✅ Thank you! Continuing chat...")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("Storage save failed. Check console for details.")
    
    # Chat Input
    if question := st.chat_input("Ask anything...", 
                                  disabled=bool(st.session_state.lead_capture_mode and not st.session_state.lead_captured)):
        if st.session_state.lead_capture_mode and not st.session_state.lead_captured:
            st.warning("⚠️ Please complete the form above")
        else:
            st.session_state.chat_history.append({"role": "user", "content": question})
            
            with st.spinner("Thinking..."):
                answer = bot.ask(question)
            
            st.session_state.chat_history.append({"role": "assistant", "content": answer})
            st.session_state.question_count += 1
            
            # Trigger lead capture after 3 questions
            if st.session_state.question_count >= 3 and not st.session_state.lead_captured and not st.session_state.lead_capture_mode:
                st.session_state.lead_capture_mode = 'ask_name'
            
            st.rerun()


if __name__ == "__main__":
    main()

