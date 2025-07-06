# 📚 English Exam Automation

매일 자동으로 영어 시험지를 생성하고 Slack으로 전송하는 시스템

## 🎯 기능

- 📝 Excel 파일에서 무작위로 30개 단어 선택
- 📋 5개 섹션으로 구성된 종합 시험지 생성
- ✅ 정답지 자동 생성
- 📤 Slack 채널로 자동 전송
- 🕘 매일 오전 9시 자동 실행

## 📊 시험지 구성

- **Section 1**: 영→한 번역 (15문제, 30점)
- **Section 2**: 한→영 번역 (15문제, 30점)
- **Section 3**: 영작문 (5문제, 20점)
- **Section 4**: 문맥 번역 (5문제, 30점)
- **Section 5**: 동의어 선택 (10문제, 20점)

**총 50문제, 100점 만점**

## 🛠️ 설치 및 설정

### 1. 저장소 클론
```bash
git clone https://github.com/lilly-pad99/english-exam-automation.git
cd english-exam-automation 
