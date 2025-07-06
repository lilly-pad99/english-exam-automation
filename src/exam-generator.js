 const XLSX = require('xlsx');
const fs = require('fs');
const path = require('path');

class ExamGenerator {
    constructor(excelPath) {
        this.excelPath = excelPath;
        this.vocabData = this.loadVocabData();
        this.synonymsDB = this.initSynonymsDB();
    }

    loadVocabData() {
        try {
            const workbook = XLSX.readFile(this.excelPath);
            const worksheet = workbook.Sheets[workbook.SheetNames[0]];
            const jsonData = XLSX.utils.sheet_to_json(worksheet, { header: 1 });
            
            const dataRows = jsonData.slice(1).filter(row => row.length > 0);
            const validData = [];

            dataRows.forEach((row) => {
                const englishExpression = row[0];
                const meaning = row[1];
                const usage = row[2];
                
                if (englishExpression && englishExpression.trim()) {
                    validData.push({
                        english: englishExpression.trim(),
                        meaning: meaning ? meaning.trim() : '',
                        usage: usage ? usage.trim() : ''
                    });
                }
            });

            return validData.filter(item => item.meaning);
        } catch (error) {
            console.error('Excel 파일 로드 중 오류:', error);
            return [];
        }
    }

    initSynonymsDB() {
        return {
            'business': ['company', 'enterprise', 'firm', 'corporation'],
            'secure': ['obtain', 'acquire', 'get', 'gain'],
            'secured': ['obtained', 'acquired', 'gained', 'attained'],
            'moguls': ['tycoons', 'magnates', 'barons', 'bigwigs'],
            'latitude': ['freedom', 'leeway', 'flexibility', 'scope'],
            'pending': ['awaiting', 'unresolved', 'outstanding', 'in progress'],
            'profit': ['benefit', 'gain', 'earnings', 'revenue'],
            'boast': ['brag', 'show off', 'flaunt', 'pride oneself'],
            'considerable': ['substantial', 'significant', 'notable', 'major'],
            'allegations': ['accusations', 'charges', 'claims', 'assertions'],
            'analyst': ['examiner', 'researcher', 'investigator', 'specialist'],
            'reputation': ['image', 'standing', 'prestige', 'status'],
            'facility': ['building', 'premises', 'establishment', 'center'],
            'embark on': ['begin', 'start', 'commence', 'initiate'],
            'curry favor': ['flatter', 'suck up', 'brown-nose', 'butter up'],
            'resilient': ['robust', 'durable', 'tough', 'adaptable']
        };
    }

    shuffleArray(array) {
        const shuffled = [...array];
        for (let i = shuffled.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
        }
        return shuffled;
    }

    generateExam() {
        const shuffledWords = this.shuffleArray(this.vocabData);
        const selectedWords = shuffledWords.slice(0, 30);
        
        return {
            section1Words: selectedWords.slice(0, 15),
            section2Words: selectedWords.slice(15, 30),
            section3Words: this.shuffleArray([...selectedWords]).slice(0, 5),
            section4Words: this.shuffleArray([...selectedWords]).slice(0, 5),
            section5Words: this.shuffleArray([...selectedWords]).slice(0, 10),
            allUsedWords: selectedWords
        };
    }

    generateExamFile() {
        const examData = this.generateExam();
        const today = new Date().toISOString().split('T')[0];
        
        const examContent = this.createExamContent(examData, today);
        const answerContent = this.createAnswerContent(examData, today);
        
        // 파일 저장
        fs.writeFileSync(`exam_${today}.md`, examContent);
        fs.writeFileSync(`answers_${today}.md`, answerContent);
        
        console.log(`✅ 시험지 생성 완료: exam_${today}.md`);
        console.log(`✅ 답지 생성 완료: answers_${today}.md`);
        
        return {
            examFile: `exam_${today}.md`,
            answerFile: `answers_${today}.md`
        };
    }

    createExamContent(examData, date) {
        const { section1Words, section2Words, section3Words, section4Words, section5Words } = examData;
        
        return `# 영어 통역사 대비 시험지
**날짜**: ${date}  
**제한시간**: 60분  
**총점**: 100점

---

## Section 1: 영한 번역 (15문제, 각 2점)
**지시사항**: 다음 영어 표현의 한국어 의미를 적으시오.

${section1Words.map((word, index) => 
    `${index + 1}. **${word.english}** → (                    )`
).join('\n')}

---

## Section 2: 한영 번역 (15문제, 각 2점)
**지시사항**: 다음 한국어를 적절한 영어 표현으로 번역하시오.

${section2Words.map((word, index) => 
    `${index + 1}. **${word.meaning}** → (                    )`
).join('\n')}

---

## Section 3: 영작문 (5문제, 각 4점)
**지시사항**: 주어진 단어를 활용하여 영어 문장을 작성하시오.

${section3Words.map((word, index) => 
    `${index + 1}. **${word.english}** 활용 문장:\n   _________________________________________________`
).join('\n\n')}

---

## Section 4: 문맥 번역 (5문제, 각 6점)
**지시사항**: 주어진 문맥에서 밑줄 친 부분을 자연스럽게 번역하시오.

${section4Words.map((word, index) => 
    `${index + 1}. **문맥**: "The company **${word.english}** in a competitive market."\n   번역: _________________________________________________`
).join('\n\n')}

---

## Section 5: 동의어 선택 (10문제, 각 2점)
**지시사항**: 주어진 단어와 의미가 가장 유사한 단어를 고르시오.

${section5Words.map((word, index) => {
    const synonyms = this.getSynonyms(word.english);
    const options = this.shuffleArray([synonyms[0], 'distractor1', 'distractor2', 'distractor3']);
    return `${index + 1}. **${word.english}** 와 의미가 가장 유사한 것은?\n   ① ${options[0]}  ② ${options[1]}  ③ ${options[2]}  ④ ${options[3]}`;
}).join('\n\n')}

---

**시험 종료**  
**총 문제 수**: 50문제  
**만점**: 100점`;
    }

    createAnswerContent(examData, date) {
        const { section1Words, section2Words, section3Words, section4Words, section5Words } = examData;
        
        return `# 영어 통역사 대비 시험지 - 정답지
**날짜**: ${date}

---

## Section 1: 영한 번역 정답 (각 2점)

${section1Words.map((word, index) => 
    `${index + 1}. **${word.english}** → **${word.meaning}**`
).join('\n')}

---

## Section 2: 한영 번역 정답 (각 2점)

${section2Words.map((word, index) => 
    `${index + 1}. **${word.meaning}** → **${word.english}**`
).join('\n')}

---

## Section 3: 영작문 예시 답안 (각 4점)

${section3Words.map((word, index) => 
    `${index + 1}. **${word.english}** 활용:\n   - **예시**: "The company ${word.english} successfully in the market."\n   - **채점 기준**: 단어 활용의 정확성, 문법적 올바름, 의미 전달`
).join('\n\n')}

---

## Section 4: 문맥 번역 정답 (각 6점)

${section4Words.map((word, index) => 
    `${index + 1}. **정답**: "그 회사는 경쟁적인 시장에서 **${word.meaning}**했다."`
).join('\n')}

---

## Section 5: 동의어 선택 정답 (각 2점)

${section5Words.map((word, index) => {
    const synonym = this.getSynonyms(word.english)[0];
    return `${index + 1}. **${word.english}** → **${synonym}**`;
}).join('\n')}

---

**만점**: 100점  
**합격선**: 70점 (통역사 수준)`;
    }

    getSynonyms(word) {
        const key = word.toLowerCase();
        return this.synonymsDB[key] || ['synonym1', 'synonym2', 'synonym3', 'similar_word'];
    }
}

// 실행부
if (require.main === module) {
    const generator = new ExamGenerator('./data/vocabs.xlsx');
    const files = generator.generateExamFile();
    console.log('시험지 생성 완료:', files);
}

module.exports = ExamGenerator;
