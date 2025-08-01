#!/usr/bin/env python3
"""
통합 영어 학습 자동화 시스템
- Phase 2: 뉴욕타임스 기사 추출
- Phase 3: AI 번역 및 학습 자료 생성
- Phase 4: Slack 전송
- Slack 봇: 단어 조회 및 시험지 생성
"""

import os
import re
import json
import logging
import random
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import requests

# Web Scraping
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time

# Slack SDK
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

# Google Sheets API
import gspread
from google.oauth2.service_account import Credentials

# AI APIs
import anthropic

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class NYTimesArticleExtractor:
    """뉴욕타임스 기사 추출 클래스 (Phase 2)"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.driver = None

    def _get_full_article_text(self, url: str) -> str:
        """Selenium을 사용하여 전체 기사 텍스트를 스크래핑"""
        try:
            if "/interactive/" in url or "/learning/" in url:
                logger.info(f"Skipping non-article URL: {url}")
                return ""

            logger.info(f"Selenium으로 기사 스크래핑 시작: {url}")

            # --- Chrome 옵션 설정 ---
            chrome_options = Options()
            # Using a temporary profile to avoid permission issues.
            chrome_options.add_argument("--headless") # Run in headless mode
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--log-level=3") # Suppress console logs

            # --- WebDriver 초기화 ---
            # webdriver-manager will download and manage the driver automatically
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)

            driver.get(url)
            # Wait for the page to load dynamically
            time.sleep(10)

            # --- BeautifulSoup으로 HTML 파싱 ---
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            driver.quit()

            # --- 기사 본문 추출 ---
            # NYT articles typically have their main content in a <section>
            # with the name "articleBody".
            article_body = soup.find('section', attrs={'name': 'articleBody'})
            if not article_body:
                # Fallback to other common selectors
                article_body = soup.find('div', class_='story-body') or soup.find('div', id='story')

            if not article_body:
                logger.warning("기사 본문(<section name='articleBody'>)을 찾을 수 없습니다.")
                return ""

            # Find all paragraph tags within the article body
            paragraphs = article_body.find_all('p')
            full_text = "\n\n".join(p.get_text() for p in paragraphs)

            logger.info(f"기사 스크래핑 완료, 글자 수: {len(full_text)}")
            return full_text

        except Exception as e:
            logger.error(f"Selenium 스크래핑 실패: {e}")
            if 'driver' in locals() and driver:
                driver.quit()
            return ""

    def get_daily_topic(self) -> str:
        """일별 주제 순환 (medical → politics → technology)"""
        topics = ['medical', 'politics', 'technology']
        day_of_year = datetime.now().timetuple().tm_yday
        topic = topics[day_of_year % 3]

        # 강제 주제 설정 (환경 변수)
        force_topic = os.getenv('FORCE_TOPIC', '').lower()
        if force_topic in topics:
            topic = force_topic

        return topic

    def extract_articles(self, topic: str, max_articles: int = 10) -> List[Dict]:
        """API로 기사 메타데이터를 가져오고, 웹 스크래핑으로 전체 본문 추출"""
        try:
            logger.info(f"주제 '{topic}'에서 4개 이상 문단이 있는 기사 추출 시작")

            if not self.api_key:
                logger.error("NYT API 키가 설정되지 않았습니다.")
                return []

            # NYT API를 사용하여 기사 검색
            url = f"https://api.nytimes.com/svc/search/v2/articlesearch.json?q={topic}&api-key={self.api_key}"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            if not data.get("response", {}).get("docs"):
                logger.warning("API에서 기사를 찾을 수 없습니다")
                return []

            for entry in data["response"]["docs"]:
                try:
                    article_url = entry.get('web_url')
                    if not article_url:
                        continue

                    # 웹 스크래핑으로 전체 기사 본문 가져오기
                    full_content = self._get_full_article_text(article_url)
                    if not full_content:
                        logger.warning(f"기사 본문을 가져올 수 없습니다: {entry['headline']['main']}")
                        continue

                    # 본문을 문단으로 분리
                    # Split by double newlines, which is how we joined them
                    paragraphs = [p.strip() for p in full_content.split('\n\n') if p.strip()]
                    word_count = len(full_content.split())


                    # 품질 기준 확인 (문단 4개 이상, 단어 500개 이상)
                    if len(paragraphs) >= 4 and word_count >= 500:
                        article = {
                            "selected_date": datetime.now().strftime("%Y-%m-%d"),
                            "daily_topic": topic,
                            "article": {
                                "title": entry['headline']['main'],
                                "link": article_url,
                                "topic": topic,
                                "published": entry['pub_date'],
                                "quality_score": 100, # Scraped articles are high quality
                                "content": {
                                    "paragraphs": paragraphs,
                                    "total_paragraphs": len(paragraphs),
                                    "word_count": word_count
                                }
                            }
                        }
                        logger.info(f"전체 기사 추출 완료: {article['article']['title']}")
                        return [article] # 첫 번째 기준 충족 기사 반환

                except Exception as e:
                    logger.warning(f"기사 처리 실패: {e}")
                    continue

            logger.warning("기준을 충족하는 기사를 찾지 못했습니다 (문단 4개 이상, 단어 500개 이상).")
            return []

        except Exception as e:
            logger.error(f"기사 추출 실패: {e}")
            return []
    
    

class AIArticleProcessor:
    """AI 기사 처리 클래스 (Phase 3)"""
    
    def __init__(self, anthropic_api_key: str):
        self.client = anthropic.Anthropic(api_key=anthropic_api_key)
    
    def process_article(self, article_data: Dict) -> Dict:
        """기사를 학습 자료로 처리"""
        try:
            logger.info("Phase 3: AI 처리 시작")
            
            article = article_data.get('article', {})
            paragraphs = article.get('content', {}).get('paragraphs', [])
            
            if not paragraphs:
                return {'success': False, 'error': '문단이 부족합니다'}
            
            # 번역할 문단 선택 (마지막 2개)
            translation_indices = self._select_translation_paragraphs(paragraphs, 2)
            
            # 혼합 콘텐츠 생성
            mixed_content = self._create_mixed_content(paragraphs, translation_indices, article)
            
            # 해설 자료 생성
            commentary_data = self._create_commentary_data(paragraphs, translation_indices, article)
            
            # 파일 저장
            mixed_file = self._save_mixed_content(mixed_content)
            commentary_file = self._save_commentary_data(commentary_data)
            
            return {
                'success': True,
                'article_title': article.get('title', ''),
                'topic': article.get('topic', ''),
                'mixed_content_file': mixed_file,
                'commentary_file': commentary_file,
                'mixed_content_data': mixed_content,
                'commentary_data': commentary_data
            }
            
        except Exception as e:
            logger.error(f"AI 처리 실패: {e}")
            return {'success': False, 'error': str(e)}
    
    def _select_translation_paragraphs(self, paragraphs: List[str], count: int = 2) -> List[int]:
        """번역할 문단 선택 (마지막 2개)"""
        total = len(paragraphs)
        if total <= count:
            return list(range(total))
        
        return list(range(total - count, total))
    
    def _create_mixed_content(self, paragraphs: List[str], translation_indices: List[int], article: Dict) -> Dict:
        """혼합 콘텐츠 생성 (영어 + 한글)"""
        mixed_paragraphs = []
        
        for i, paragraph in enumerate(paragraphs):
            if i in translation_indices:
                # 한글 번역
                korean_text = self._translate_to_korean(paragraph, article.get('topic', ''))
                mixed_paragraphs.append({
                    'paragraph_number': i + 1,
                    'type': 'korean',
                    'content': korean_text
                })
            else:
                # 영어 원문
                mixed_paragraphs.append({
                    'paragraph_number': i + 1,
                    'type': 'english',
                    'content': paragraph
                })
        
        korean_indices = [i + 1 for i in translation_indices]
        
        return {
            "title": article.get('title', ''),
            "source": "New York Times",
            "topic": article.get('topic', ''),
            "published_date": article.get('published', ''),
            "processing_date": datetime.now().isoformat(),
            "content_structure": {
                "total_paragraphs": len(mixed_paragraphs),
                "english_paragraphs": len(paragraphs) - len(translation_indices),
                "korean_paragraphs": len(translation_indices),
                "translation_indices": korean_indices
            },
            "paragraphs": mixed_paragraphs,
            "reading_instruction": "영어 문단은 이해하며 읽고, 한글 문단은 영어로 번역해보세요."
        }
    
    def _create_commentary_data(self, paragraphs: List[str], translation_indices: List[int], article: Dict) -> Dict:
        """해설 및 통역 연습 자료 생성"""
        # 영어 문단에서 표현 추출
        english_paragraphs = [p for i, p in enumerate(paragraphs) if i not in translation_indices]
        expressions = self._extract_expressions(' '.join(english_paragraphs), article.get('topic', ''))
        
        # 한글 문단으로 통역 연습 생성
        translation_exercises = []
        for i in translation_indices:
            if i < len(paragraphs):
                korean_text = self._translate_to_korean(paragraphs[i], article.get('topic', ''))
                exercise = self._create_translation_exercise(korean_text, i + 1, article)
                translation_exercises.append(exercise)
        
        return {
            "title": f"해설 및 통역 연습 - {article.get('title', '')}",
            "source_article": {
                "title": article.get('title', ''),
                "topic": article.get('topic', ''),
                "url": article.get('link', '')
            },
            "processing_date": datetime.now().isoformat(),
            "part_1_expressions": {
                "description": "원문에서 추출한 중요 영어 표현 10개",
                "expressions": expressions[:10]
            },
            "part_2_translation_practice": {
                "description": "한글 문단의 통역 연습 (한→영)",
                "korean_paragraphs": [i + 1 for i in translation_indices],
                "translation_exercises": translation_exercises
            }
        }
    
    def _translate_to_korean(self, text: str, context: str) -> str:
        """영어를 한글로 번역"""
        try:
            prompt = f"""
다음 영어 문단을 자연스럽고 정확한 한국어로 번역해주세요.

주제: {context}
원문: {text}

번역할 때 고려사항:
- 자연스러운 한국어 표현 사용
- 전문 용어는 적절한 한국어 용어로 번역
- 문맥과 뉘앙스 유지
- 읽기 쉬운 문장 구조로 번역

번역문만 제공해주세요.
"""

            response = self.client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=500,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            
            return response.content[0].text.strip()
            
        except Exception as e:
            logger.error(f"번역 실패: {e}")
            return text  # 실패 시 원문 반환
    
    def _extract_expressions(self, text: str, topic: str) -> List[Dict]:
        """영어 표현 추출"""
        try:
            prompt = f"""
다음 영어 텍스트에서 중요하고 유용한 표현 10개를 추출하여 JSON 배열로 제공해주세요.

주제: {topic}
텍스트: {text}

각 표현에 대해 다음 정보를 포함해주세요:
{{
    "expression": "추출된 표현",
    "korean_meaning": "한글 의미",
    "synonyms": ["동의어1", "동의어2", "동의어3"],
    "context": "원문에서의 사용 예",
    "usage_note": "사용법 설명",
    "formality": "격식도 (격식체/비격식체/전문용어)"
}}

응답은 JSON 배열 형태로만 제공해주세요.
"""

            response = self.client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=2000,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.content[0].text.strip()
            
            # JSON 파싱
            try:
                json_str = content
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0]
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0]
                
                start_index = json_str.find('[')
                end_index = json_str.rfind(']')
                
                if start_index != -1 and end_index != -1:
                    json_str = json_str[start_index:end_index+1]
                    return json.loads(json_str)
                
                logger.warning("Could not find JSON array in the response.")
                return []

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON: {e}")
                logger.error(f"Response content: {content}")
                return []
            
        except Exception as e:
            logger.error(f"표현 추출 실패: {e}")
            return []
    
    def _create_translation_exercise(self, korean_text: str, paragraph_number: int, article: Dict) -> Dict:
        """통역 연습 생성"""
        try:
            escaped_korean_text = json.dumps(korean_text, ensure_ascii=False)
            
            prompt = f"""
다음 한글 문장을 영어로 번역하는 통역 연습을 만들어주세요.

주제: {article.get('topic', '')}
한글 문장: {korean_text}

다음 형식으로 JSON 응답해주세요:
{{
    "paragraph_number": {paragraph_number},
    "korean_text": {escaped_korean_text},
    "interpretation_approach": "통역 관점에서의 번역 접근법",
    "key_challenges": ["번역 시 주의할 점1", "주의할 점2", "주의할 점3"],
    "professional_translation": "모범 번역문",
    "alternative_versions": ["대안 번역1", "대안 번역2"],
    "interpretation_notes": ["통역 팁1", "통역 팁2", "통역 팁3"]
}}
"""

            response = self.client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=1000,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.content[0].text.strip()
            
            # JSON 파싱
            try:
                json_str = content
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0]
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0]
                
                start_index = json_str.find('{')
                end_index = json_str.rfind('}')
                
                if start_index != -1 and end_index != -1:
                    json_str = json_str[start_index:end_index+1]
                    return json.loads(json_str)
                
                logger.warning("Could not find JSON object in the response.")
                return {
                    "paragraph_number": paragraph_number,
                    "korean_text": korean_text,
                    "professional_translation": "Translation exercise could not be generated"
                }

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON: {e}")
                logger.error(f"Response content: {content}")
                return {
                    "paragraph_number": paragraph_number,
                    "korean_text": korean_text,
                    "professional_translation": "Translation exercise could not be generated"
                }
            
        except Exception as e:
            logger.error(f"통역 연습 생성 실패: {e}")
            return {
                "paragraph_number": paragraph_number,
                "korean_text": korean_text,
                "professional_translation": "Translation exercise could not be generated"
            }
    
    def _save_mixed_content(self, content: Dict) -> str:
        """혼합 콘텐츠 파일 저장"""
        os.makedirs('output', exist_ok=True)
        filename = f"output/mixed_content_{content.get('topic', 'general')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
        
        return filename
    
    def _save_commentary_data(self, content: Dict) -> str:
        """해설 자료 파일 저장"""
        os.makedirs('output', exist_ok=True)
        filename = f"output/commentary_{content.get('source_article', {}).get('topic', 'general')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
        
        return filename

class SlackNotifier:
    """Slack 전송 클래스 (Phase 4)"""
    
    def __init__(self, bot_token: str, channel: str):
        self.client = WebClient(token=bot_token)
        self.channel = channel
    
    def send_daily_materials(self, mixed_content_data: Dict, commentary_data: Dict) -> Dict:
        """일일 학습 자료 전송"""
        try:
            results = {
                'mixed_content_sent': False,
                'commentary_sent': False,
                'errors': []
            }
            
            # 1. 혼합 콘텐츠 전송
            mixed_messages = self._format_mixed_content_message(mixed_content_data)
            try:
                for message in mixed_messages:
                    response = self.client.chat_postMessage(
                        channel=self.channel,
                        **message
                    )
                results['mixed_content_sent'] = True
                logger.info("혼합 콘텐츠 전송 완료")
            except SlackApiError as e:
                logger.error(f"혼합 콘텐츠 전송 실패: {e.response['error']}")
                results['errors'].append(f"혼합 콘텐츠 전송 실패: {e}")
            
            # 2. 해설 자료 전송
            commentary_message = self._format_commentary_message(commentary_data)
            try:
                response = self.client.chat_postMessage(
                    channel=self.channel,
                    **commentary_message
                )
                results['commentary_sent'] = True
                logger.info("해설 자료 전송 완료")
            except SlackApiError as e:
                logger.error(f"해설 자료 전송 실패: {e.response['error']}")
                results['errors'].append(f"해설 자료 전송 실패: {e}")
            
            logger.info(f"Slack 전송 결과: {results}")
            return results
            
        except Exception as e:
            logger.error(f"Slack 전송 실패: {e}")
            return {'mixed_content_sent': False, 'commentary_sent': False, 'errors': [str(e)]}
    
    def _format_mixed_content_message(self, data: Dict) -> List[Dict]:
        """혼합 콘텐츠 메시지 포맷팅"""
        title = data.get('title', '')
        topic = data.get('topic', '').title()
        published_date = data.get('published_date', '')[:10]
        
        header_text = (
            f"📰 *오늘의 영어 기사* ({topic})\n"
            f"*제목:* {title}\n"
            f"*출처:* New York Times | *날짜:* {published_date}\n\n"
        )
        
        content_text = "=" * 50 + "\n\n"
        
        for para in data.get('paragraphs', []):
            para_num = para.get('paragraph_number', 0)
            para_type = para.get('type', 'english')
            
            if para_type == 'korean':
                content_text += f"*🇰🇷 문단 {para_num} (한글)*\n"
                content_text += f"{para.get('content', '')}\n\n"
            else:
                content_text += f"*📖 문단 {para_num} (영어)*\n"
                content_text += f"{para.get('content', '')}\n\n"
        
        structure = data.get('content_structure', {})
        footer_text = (
            "=" * 50 + "\n"
            f"💡 *학습 팁:* 영어 문단은 이해하며 읽고, 한글 문단은 영어로 번역해보세요!\n"
            f"📊 *구성:* 총 {structure.get('total_paragraphs', 0)}문단 중 "
            f"영어 {structure.get('english_paragraphs', 0)}개, "
            f"한글 {structure.get('korean_paragraphs', 0)}개"
        )
        
        full_text = header_text + content_text + footer_text
        
        # Split the message into chunks of 2500 characters
        chunks = []
        while len(full_text) > 2500:
            split_pos = full_text.rfind("\n\n", 0, 2500)
            if split_pos == -1:
                split_pos = 2500
            chunks.append(full_text[:split_pos])
            full_text = full_text[split_pos:]
        chunks.append(full_text)
        
        messages = []
        for chunk in chunks:
            messages.append({
                "text": chunk,
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": chunk
                        }
                    }
                ]
            })
        
        return messages
    
    def _format_commentary_message(self, data: Dict) -> Dict:
        """해설 자료 메시지 포맷팅"""
        expressions = data.get('part_1_expressions', {}).get('expressions', [])[:10]
        
        header_text = (
            f"📚 *오늘의 영어 표현 해설*\n"
            f"*출처:* {data.get('source_article', {}).get('title', '')}\n\n"
            f"*🎯 원문에서 추출한 핵심 표현*\n\n"
        )
        
        expressions_text = ""
        
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        for i, expr in enumerate(expressions, 1):
            if i > len(emojis):
                break
            emoji_num = emojis[i-1]
            expressions_text += f"*{emoji_num} {expr.get('expression', '')}*\n"
            expressions_text += f"🇰🇷 *뜻:* {expr.get('korean_meaning', '')}\n"
            
            if expr.get('synonyms'):
                synonyms_text = ', '.join(expr['synonyms'][:2])
                expressions_text += f"🔄 *동의어:* {synonyms_text}\n"
            
            if expr.get('context'):
                context_preview = expr['context'][:60] + "..." if len(expr['context']) > 60 else expr['context']
                expressions_text += f"📝 *예문:* {context_preview}\n"
            
            expressions_text += "\n"
        
        full_text = header_text + expressions_text
        
        return {
            "text": full_text,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": full_text
                    }
                }
            ]
        }

class VocabBot:
    """영어 단어 봇 클래스"""
    
    def __init__(self, slack_bot_token: str, slack_app_token: str, 
                 anthropic_api_key: str, google_service_account_file: str,
                 spreadsheet_id: str):
        
        # Slack 설정
        self.app = App(token=slack_bot_token)
        self.client = WebClient(token=slack_bot_token)
        self.socket_handler = SocketModeHandler(self.app, slack_app_token)
        
        # Claude 설정
        self.claude_client = anthropic.Anthropic(api_key=anthropic_api_key)
        
        # Google Sheets 설정
        self.setup_google_sheets(google_service_account_file, spreadsheet_id)
        
        # 이벤트 핸들러 등록
        self.register_handlers()
    
    def setup_google_sheets(self, service_account_file: str, spreadsheet_id: str):
        """Google Sheets 연결 설정"""
        try:
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            
            creds = Credentials.from_service_account_file(
                service_account_file, scopes=scope
            )
            self.gc = gspread.authorize(creds)
            self.spreadsheet = self.gc.open_by_key(spreadsheet_id)
            self.worksheet = self.spreadsheet.worksheet('시트1')
            
            logger.info("Google Sheets 연결 성공")
            
        except Exception as e:
            logger.error(f"Google Sheets 연결 실패: {e}")
            raise
    
    def register_handlers(self):
        """이벤트 핸들러 등록"""
        
        @self.app.message(re.compile(r"^@(\S+)"))
        def handle_vocab_query(message, say, context):
            """@단어 명령어 처리"""
            try:
                word = context['matches'][0].strip()
                
                if not word:
                    say("❌ 단어를 입력해주세요. 예: @hello")
                    return
                
                say(f"🔍 '{word}' 검색 중...")
                
                # 단어 정보 조회
                word_info = self.get_word_definition(word)
                
                if not word_info:
                    say(f"❌ '{word}'의 정보를 찾을 수 없습니다.")
                    return
                
                # Google Sheets에 추가
                success = self.add_to_sheet(word_info)
                
                # 결과 메시지 생성
                result_message = self.format_vocab_response(word_info, success)
                say(result_message)
                
            except Exception as e:
                logger.error(f"단어 처리 중 오류: {e}")
                say(f"❌ 처리 중 오류가 발생했습니다: {str(e)}")
        
        @self.app.message(re.compile(r"(?:^시험지|^test paper)\s*(\d+)?(?:\s+s1=(\d+))?(?:\s+s2=(\d+))?(?:\s+s3=(\d+))?(?:\s+s4=(\d+))?(?:\s+s5=(\d+))?"))
        def handle_exam_generation(message, say, context):
            """시험지 생성 명령어 처리"""
            try:
                matches = context['matches']
                total_count_str = matches[0]
                s1_str = matches[1]
                s2_str = matches[2]
                s3_str = matches[3]
                s4_str = matches[4]
                s5_str = matches[5]

                total_count = int(total_count_str) if total_count_str else 30
                s1 = int(s1_str) if s1_str else 15
                s2 = int(s2_str) if s2_str else 15
                s3 = int(s3_str) if s3_str else 5
                s4 = int(s4_str) if s4_str else 5
                s5 = int(s5_str) if s5_str else 10
                
                if total_count < 10 or total_count > 100:
                    say("❌ 문제 수는 10~100개 사이로 입력해주세요. 예: 시험지 30")
                    return
                
                say(f"📝 {total_count}문제 시험지 생성 중... 잠시만 기다려주세요.")
                
                # 시험지 생성
                exam_result = self.generate_exam(total_count, s1, s2, s3, s4, s5)
                
                if exam_result['success']:
                    # 시험지 파일 업로드
                    self.upload_exam_files(exam_result, message['channel'])
                    
                    result_message = f"""
📄 **시험지 생성 완료!**

📊 **구성:**
• Section 1: 영→한 번역 ({exam_result['section1_count']}문제)
• Section 2: 한→영 번역 ({exam_result['section2_count']}문제)
• Section 3: 영어 작문 ({exam_result['section3_count']}문제)
• Section 4: 문맥 번역 ({exam_result['section4_count']}문제)
• Section 5: 동의어 선택 ({exam_result['section5_count']}문제)

**총 {exam_result['total_questions']}문제**

✅ 시험지와 답지가 별도 파일로 생성되었습니다.
                    """
                    say(result_message)
                else:
                    say(f"❌ 시험지 생성 실패: {exam_result.get('error', '알 수 없는 오류')}")
                
            except ValueError:
                say("❌ 올바른 숫자를 입력해주세요. 예: 시험지 30")
            except Exception as e:
                logger.error(f"시험지 생성 중 오류: {e}")
                say(f"❌ 시험지 생성 중 오류가 발생했습니다: {str(e)}")
        
        @self.app.message("도움말")
        def handle_help(say):
            """도움말 메시지"""
            help_text = """
📚 *영어 단어 봇 사용법*

*명령어:*
• `@단어` - 영어 단어 뜻 조회 및 저장
• `시험지` 또는 `시험지 30` - 시험지 생성 (기본 30문제)
• `도움말` - 이 메시지 표시

*예시:*
• `@hello` - hello 단어 조회
• `@beautiful` - beautiful 단어 조회
• `@take care of` - 구문 조회
• `시험지` - 30문제 시험지 생성
• `시험지 50` - 50문제 시험지 생성

*단어 조회 기능:*
✅ 영어 단어/구문 의미 조회
✅ 동의어 제공
✅ 예문 제공
✅ Google Sheets 자동 저장
✅ 중복 검사

*시험지 생성 기능:*
✅ Section 1: 영→한 번역
✅ Section 2: 한→영 번역  
✅ Section 3: 영어 작문
✅ Section 4: 문맥 번역
✅ Section 5: 동의어 선택
✅ 답지 자동 생성

*저장되는 정보:*
• 영어 표현
• 한글 의미
• 동의어
            """
            say(help_text)
    
    def get_word_definition(self, word: str) -> Optional[Dict]:
        """Claude API를 통한 단어 정보 조회"""
        try:
            prompt = f"""
다음 영어 단어/표현에 대해 정확한 정보를 JSON 형태로 제공해주세요:

단어: "{word}"

다음 형식으로 응답해주세요:
{{
    "word": "단어 원형",
    "korean_meaning": "주요 한글 의미",
    "synonyms": ["동의어1", "동의어2", "동의어3"],
    "example": "영어 예문",
    "korean_example": "예문 한글 번역"
}}

주의사항:
- 가장 일반적이고 중요한 의미를 제공하세요
- 동의어는 실용적인 것들로 최대 3개까지
- 예문은 실생활에서 사용 가능한 자연스러운 문장으로
- 구문의 경우 전체를 하나의 단위로 처리
- JSON 형식을 정확히 지켜주세요
"""

            response = self.claude_client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=1000,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.content[0].text.strip()
            
            # JSON 파싱
            try:
                json_str = content
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0]
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0]
                
                start_index = json_str.find('{')
                end_index = json_str.rfind('}')
                
                if start_index != -1 and end_index != -1:
                    json_str = json_str[start_index:end_index+1]
                    word_info = json.loads(json_str)
                    
                    required_fields = ['word', 'korean_meaning']
                    if not all(field in word_info for field in required_fields):
                        logger.error(f"Missing required fields: {word_info}")
                        return None
                    
                    if not word_info.get('synonyms'):
                        word_info['synonyms'] = []
                    
                    logger.info(f"Received word info from Claude: {word_info.get('word', '')}")
                    return word_info
                
                logger.warning("Could not find JSON object in the response.")
                return None

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON: {e}")
                logger.error(f"Response content: {content}")
                return None
            
        except Exception as e:
            logger.error(f"Claude API 호출 실패: {e}")
            return None
    
    def get_random_words(self, count: int) -> List[Dict]:
        """Google Sheets에서 랜덤 단어 추출"""
        try:
            all_data = self.worksheet.get_all_values()[1:]  # 헤더 제외
            
            if len(all_data) < count:
                logger.warning(f"요청한 단어 수({count})가 저장된 단어 수({len(all_data)})보다 많습니다.")
                count = len(all_data)
            
            selected_rows = random.sample(all_data, count)
            
            words = []
            for row in selected_rows:
                if len(row) >= 3:
                    word_data = {
                        'word': row[0],
                        'meaning': row[1],
                        'synonyms': row[2].split(', ') if row[2] else []
                    }
                    words.append(word_data)
            
            logger.info(f"랜덤 단어 {len(words)}개 선택 완료")
            return words
            
        except Exception as e:
            logger.error(f"랜덤 단어 추출 실패: {e}")
            return []
    
    def generate_exam(self, total_count: int = 30, section1_count: int = 15, section2_count: int = 15, section3_count: int = 5, section4_count: int = 5, section5_count: int = 10) -> Dict:
        """시험지 생성"""
        try:
            words = self.get_random_words(total_count)
            if len(words) < 10:
                return {
                    'success': False,
                    'error': f'저장된 단어가 부족합니다. (현재: {len(words)}개, 최소: 10개 필요)'
                }
            
            # 단어 분배
            section1_words = words[:section1_count]
            section2_words = words[section1_count:total_count] if total_count >= 30 else words[section1_count:]
            if len(section2_words) < section2_count:
                section2_words.extend(words[:section2_count - len(section2_words)])
            section2_words = section2_words[:section2_count]
            
            # 작문 및 문맥용 단어 (section1, 2에서 재사용)
            composition_words = (section1_words + section2_words)[:section3_count]
            context_words = (section1_words + section2_words)[section3_count:section3_count + section4_count]
            synonym_words = [w for w in (section1_words + section2_words) if w['synonyms']][:section5_count]
            
            # 시험지 생성
            exam_content = self.create_exam_content(
                section1_words, section2_words, composition_words, 
                context_words, synonym_words
            )
            
            answer_content = self.create_answer_content(
                section1_words, section2_words, composition_words,
                context_words, synonym_words
            )
            
            return {
                'success': True,
                'exam_content': exam_content,
                'answer_content': answer_content,
                'section1_count': section1_count,
                'section2_count': section2_count,
                'section3_count': section3_count,
                'section4_count': section4_count,
                'section5_count': len(synonym_words),
                'total_questions': section1_count + section2_count + section3_count + section4_count + len(synonym_words)
            }
            
        except Exception as e:
            logger.error(f"시험지 생성 실패: {e}")
            return {'success': False, 'error': str(e)}
    
    def create_exam_content(self, section1_words, section2_words, composition_words, 
                           context_words, synonym_words) -> str:
        """시험지 내용 생성"""
        content = f"""
# 영어 실력 향상 시험지
**생성일시**: {datetime.now().strftime('%Y년 %m월 %d일 %H시 %M분')}
**총 문항수**: {len(section1_words) + len(section2_words) + 5 + 5 + len(synonym_words)}문제

---

## Section 1: 영→한 번역 ({len(section1_words)}문제)
*다음 영어 단어/표현의 한글 뜻을 쓰시오.*

"""
        
        for i, word in enumerate(section1_words, 1):
            content += f"{i}. {word['word']}\n"
            content += f"   답: ________________________\n\n"
        
        content += f"""
---

## Section 2: 한→영 번역 ({len(section2_words)}문제)
*다음 한글 뜻에 해당하는 영어 단어/표현을 쓰시오.*

"""
        
        for i, word in enumerate(section2_words, 1):
            content += f"{i}. {word['meaning']}\n"
            content += f"   답: ________________________\n\n"
        
        content += f"""
---

## Section 3: 영어 작문 (5문제)
*제시된 단어를 활용하여 영어 문장을 만드시오.*

"""
        
        for i, word in enumerate(composition_words[:5], 1):
            content += f"{i}. 제시어: **{word['word']}**\n"
            content += f"   문장: ________________________________________________\n\n"
        
        content += f"""
---

## Section 4: 문맥 번역 (5문제)
*다음 상황에서 제시된 단어를 사용하여 적절한 영어 표현을 쓰시오.*

"""
        
        contexts = [
            "비즈니스 회의에서",
            "친구와의 일상 대화에서", 
            "공식적인 이메일에서",
            "카페에서 주문할 때",
            "여행 중 호텔에서"
        ]
        
        for i, (word, context) in enumerate(zip(context_words[:5], contexts), 1):
            content += f"{i}. 상황: {context}\n"
            content += f"   단어: **{word['word']}**\n"
            content += f"   표현: ________________________________________________\n\n"
        
        if synonym_words:
            content += f"""
---

## Section 5: 동의어 선택 ({len(synonym_words)}문제)
*다음 단어의 동의어를 모두 쓰시오.*

"""
            
            for i, word in enumerate(synonym_words, 1):
                content += f"{i}. **{word['word']}**의 동의어 (최소 2개):\n"
                content += f"   답: ________________________________________________\n\n"
        
        return content
    
    def create_answer_content(self, section1_words, section2_words, composition_words,
                             context_words, synonym_words) -> str:
        """답지 내용 생성"""
        content = f"""
# 영어 실력 향상 시험지 - 정답
**생성일시**: {datetime.now().strftime('%Y년 %m월 %d일 %H시 %M분')}

---

## Section 1: 영→한 번역 정답

"""
        
        for i, word in enumerate(section1_words, 1):
            content += f"{i}. {word['word']} → **{word['meaning']}**\n"
        
        content += f"""
---

## Section 2: 한→영 번역 정답

"""
        
        for i, word in enumerate(section2_words, 1):
            content += f"{i}. {word['meaning']} → **{word['word']}**\n"
        
        content += f"""
---

## Section 3: 영어 작문 예시 답안

"""
        
        for i, word in enumerate(composition_words[:5], 1):
            content += f"{i}. {word['word']}: (예시) This example shows how to use {word['word']} correctly.\n"
        
        content += f"""
---

## Section 4: 문맥 번역 예시 답안

"""
        
        contexts = [
            "비즈니스 회의에서",
            "친구와의 일상 대화에서", 
            "공식적인 이메일에서",
            "카페에서 주문할 때",
            "여행 중 호텔에서"
        ]
        
        for i, (word, context) in enumerate(zip(context_words[:5], contexts), 1):
            content += f"{i}. {context} - {word['word']}: (상황에 맞는 표현 사용)\n"
        
        if synonym_words:
            content += f"""
---

## Section 5: 동의어 정답

"""
            
            for i, word in enumerate(synonym_words, 1):
                synonyms_text = ', '.join(word['synonyms'])
                content += f"{i}. {word['word']}: **{synonyms_text}**\n"
        
        return content
    
    def upload_exam_files(self, exam_result: Dict, channel_id: str):
        """시험지 파일을 Slack에 업로드"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # 시험지 파일
            exam_filename = f"영어시험지_{timestamp}.txt"
            with open(exam_filename, 'w', encoding='utf-8') as f:
                f.write(exam_result['exam_content'])
            
            # 답지 파일
            answer_filename = f"영어시험지_답지_{timestamp}.txt"
            with open(answer_filename, 'w', encoding='utf-8') as f:
                f.write(exam_result['answer_content'])
            
            # Slack에 파일 업로드
            self.client.files_upload_v2(
                channel=channel_id,
                file=exam_filename,
                title="영어 시험지",
                initial_comment="📝 생성된 영어 시험지입니다."
            )
            
            self.client.files_upload_v2(
                channel=channel_id,
                file=answer_filename,
                title="영어 시험지 답지", 
                initial_comment="✅ 시험지 정답입니다."
            )
            
            # 임시 파일 삭제
            import os
            os.remove(exam_filename)
            os.remove(answer_filename)
            
            logger.info("시험지 파일 업로드 완료")
            
        except Exception as e:
            logger.error(f"파일 업로드 실패: {e}")
    
    def check_duplicate(self, word: str) -> bool:
        """Google Sheets에서 중복 검사"""
        try:
            cell_list = self.worksheet.col_values(1)
            
            word_lower = word.lower()
            for cell_value in cell_list:
                if cell_value.lower() == word_lower:
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"중복 검사 실패: {e}")
            return False
    
    def add_to_sheet(self, word_info: Dict) -> bool:
        """Google Sheets에 단어 정보 추가"""
        try:
            word = word_info.get('word', '')
            
            if self.check_duplicate(word):
                logger.info(f"중복 단어 감지: {word}")
                return False
            
            next_row = len(self.worksheet.col_values(1)) + 1
            
            synonyms = word_info.get('synonyms', [])
            synonyms_text = ', '.join(synonyms) if synonyms else ''
            
            row_data = [
                word_info.get('word', ''),
                word_info.get('korean_meaning', ''),
                synonyms_text
            ]
            
            self.worksheet.insert_row(row_data, next_row)
            logger.info(f"단어 추가 성공: {word} (행 {next_row})")
            
            return True
            
        except Exception as e:
            logger.error(f"시트 추가 실패: {e}")
            return False
    
    def format_vocab_response(self, word_info: Dict, save_success: bool) -> str:
        """단어 응답 메시지 포맷팅"""
        word = word_info.get('word', '')
        meaning = word_info.get('korean_meaning', '')
        synonyms = word_info.get('synonyms', [])
        example = word_info.get('example', '')
        korean_example = word_info.get('korean_example', '')
        
        response = f"📚 *{word}*\n"
        response += f"🇰🇷 *뜻:* {meaning}\n"
        
        if synonyms:
            response += f"🔄 *동의어:* {', '.join(synonyms)}\n"
        
        if example:
            response += f"\n💬 *예문:*\n> {example}\n"
            if korean_example:
                response += f"> _{korean_example}_\n"
        
        response += "\n" + "="*30 + "\n"
        
        if save_success:
            response += "✅ *Google Sheets에 저장 완료!*"
        else:
            response += "ℹ️ *이미 저장된 단어입니다.*"
        
        return response
    
    def start(self):
        """봇 시작"""
        logger.info("영어 단어 봇 시작...")
        self.socket_handler.start()

class IntegratedEnglishSystem:
    """통합 영어 학습 시스템"""
    
    def __init__(self, config: Dict):
        self.config = config
        
        # 컴포넌트 초기화
        self.article_extractor = NYTimesArticleExtractor(
            api_key=config.get('nyt_api_key')
        )
        
        self.ai_processor = AIArticleProcessor(
            anthropic_api_key=config['anthropic_api_key']
        )
        
        self.slack_notifier = SlackNotifier(
            bot_token=config['slack_bot_token'],
            channel=config['slack_channel']
        )
        
        # Slack 봇 (선택적)
        if config.get('enable_vocab_bot', True):
            if config.get('slack_app_token'):
                self.vocab_bot = VocabBot(
                    slack_bot_token=config['slack_bot_token'],
                    slack_app_token=config['slack_app_token'],
                    anthropic_api_key=config['anthropic_api_key'],
                    google_service_account_file=config['google_service_account_file'],
                    spreadsheet_id=config['google_spreadsheet_id']
                )
            else:
                logger.warning("SLACK_APP_TOKEN not provided. VocabBot will be disabled.")
                self.vocab_bot = None
        else:
            self.vocab_bot = None
    
    def run_daily_pipeline(self) -> Dict:
        """일일 파이프라인 실행"""
        try:
            logger.info("=== 영어 학습 자동화 파이프라인 시작 ===")
            
            # Phase 2: 기사 추출
            logger.info("Phase 2: 뉴욕타임스 기사 추출")
            topics = ['medical', 'politics', 'technology']
            daily_topic = self.article_extractor.get_daily_topic()
            topics.remove(daily_topic)
            topics.insert(0, daily_topic)

            articles = []
            for topic in topics:
                logger.info(f"오늘의 주제: {topic}")
                articles = self.article_extractor.extract_articles(topic)
                if articles:
                    break

            if not articles:
                return {'success': False, 'error': 'Phase 2: 기사 추출 실패'}
            
            # Phase 3: AI 처리
            logger.info("Phase 3: AI 번역 및 학습 자료 생성")
            ai_result = self.ai_processor.process_article(articles[0])
            
            if not ai_result.get('success'):
                return {'success': False, 'error': f"Phase 3: {ai_result.get('error')}"}
            
            # Phase 4: Slack 전송
            logger.info("Phase 4: Slack 학습 자료 전송")
            slack_result = self.slack_notifier.send_daily_materials(
                ai_result['mixed_content_data'],
                ai_result['commentary_data']
            )
            
            logger.info("=== 일일 파이프라인 완료 ===")
            
            return {
                'success': True,
                'topic': daily_topic,
                'article_title': ai_result['article_title'],
                'slack_sent': slack_result['mixed_content_sent'] and slack_result['commentary_sent'],
                'files': {
                    'mixed_content': ai_result['mixed_content_file'],
                    'commentary': ai_result['commentary_file']
                }
            }
            
        except Exception as e:
            logger.error(f"파이프라인 실행 실패: {e}")
            return {'success': False, 'error': str(e)}
    
    def start_vocab_bot(self):
        """Slack 단어 봇 시작"""
        if self.vocab_bot:
            logger.info("Slack 단어 봇 시작")
            self.vocab_bot.start()
        else:
            logger.warning("단어 봇이 비활성화되어 있습니다")

import argparse

def main():
    """메인 실행 함수"""
    parser = argparse.ArgumentParser(description='Integrated English Learning System')
    parser.add_argument('--mode', type=str, default='pipeline', choices=['pipeline', 'bot', 'both'], help='Execution mode')
    parser.add_argument('--anthropic-api-key', type=str, help='Anthropic API Key')
    parser.add_argument('--slack-bot-token', type=str, help='Slack Bot Token')
    parser.add_argument('--slack-app-token', type=str, help='Slack App Token')
    parser.add_argument('--slack-channel', type=str, default='#english-learning', help='Slack Channel')
    parser.add_argument('--google-service-account-file', type=str, default='service_account.json', help='Google Service Account File')
    parser.add_argument('--google-spreadsheet-id', type=str, help='Google Spreadsheet ID')
    parser.add_argument('--nyt-api-key', type=str, help='New York Times API Key')
    parser.add_argument('--enable-vocab-bot', type=str, default='true', help='Enable Vocab Bot')

    args = parser.parse_args()

    # UTF-8 인코딩 설정
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    # 환경 변수 로드
    config = {
        'anthropic_api_key': args.anthropic_api_key or os.getenv('ANTHROPIC_API_KEY'),
        'slack_bot_token': args.slack_bot_token or os.getenv('SLACK_BOT_TOKEN'),
        'slack_app_token': args.slack_app_token or os.getenv('SLACK_APP_TOKEN'),
        'slack_channel': args.slack_channel or os.getenv('SLACK_CHANNEL', '#english-learning'),
        'google_service_account_file': args.google_service_account_file or os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE', 'service_account.json'),
        'google_spreadsheet_id': args.google_spreadsheet_id or os.getenv('GOOGLE_SPREADSHEET_ID'),
        'nyt_api_key': args.nyt_api_key or os.getenv('NYT_API_KEY'),
        'enable_vocab_bot': (args.enable_vocab_bot or os.getenv('ENABLE_VOCAB_BOT', 'true')).lower() == 'true'
    }

    # 필수 환경 변수 검사
    required_vars = ['anthropic_api_key', 'slack_bot_token', 'google_spreadsheet_id']
    missing_vars = [var for var in required_vars if not config[var]]

    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        print("\nRequired environment variables:")
        print("- ANTHROPIC_API_KEY: Claude API Key")
        print("- SLACK_BOT_TOKEN: Slack Bot Token")
        print("- SLACK_APP_TOKEN: Slack App Token (for bot mode)")
        print("- GOOGLE_SPREADSHEET_ID: Google Sheets ID")
        print("- SLACK_CHANNEL: Slack Channel (optional)")
        print("- NYT_API_KEY: New York Times API Key (optional)")
        return

    try:
        system = IntegratedEnglishSystem(config)

        # 실행 모드 선택
        mode = args.mode

        if mode == 'bot':
            # 단어 봇만 실행
            print("🤖 Slack 단어 봇 모드로 실행")
            system.start_vocab_bot()

        elif mode == 'pipeline':
            # 일일 파이프라인 실행
            print("📰 일일 학습 자료 파이프라인 실행")
            result = system.run_daily_pipeline()

            if result['success']:
                print("✅ 파이프라인 실행 성공!")
                print(f"주제: {result['topic']}")
                print(f"기사: {result['article_title']}")
                print(f"Slack 전송: {'성공' if result['slack_sent'] else '실패'}")
            else:
                print(f"❌ 파이프라인 실행 실패: {result['error']}")

        elif mode == 'both':
            # 파이프라인 실행 후 봇 시작
            print("🔄 파이프라인 + 봇 통합 모드")

            # 파이프라인 실행
            result = system.run_daily_pipeline()
            print(f"파이프라인 결과: {'성공' if result['success'] else '실패'}")

            # 봇 시작
            system.start_vocab_bot()

        else:
            print("❌ 잘못된 실행 모드. RUN_MODE를 'pipeline', 'bot', 'both' 중 하나로 설정하세요.")

    except KeyboardInterrupt:
        print("\n👋 시스템을 종료합니다...")
    except Exception as e:
        logger.error(f"시스템 실행 오류: {e}")
        print(f"❌ 오류: {e}")

if __name__ == "__main__":
    main()