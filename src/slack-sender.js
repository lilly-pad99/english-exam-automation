 const { WebClient } = require('@slack/web-api');
const fs = require('fs');

class SlackSender {
    constructor(token, channel) {
        this.slack = new WebClient(token);
        this.channel = channel;
    }

    async sendExamFiles(examFile, answerFile) {
        try {
            const today = new Date().toLocaleDateString('ko-KR');
            
            console.log('📤 Slack에 시험지 전송 시작...');
            
            // 시험지 전송
            await this.slack.files.uploadV2({
                channel_id: this.channel,
                file: fs.createReadStream(examFile),
                filename: examFile,
                title: `📝 영어 시험지 - ${today}`,
                initial_comment: `📚 **오늘의 영어 통역사 대비 시험지**\n날짜: ${today}\n제한시간: 60분\n총 50문제 (100점 만점)\n\n화이팅! 💪`
            });

            console.log('✅ 시험지 전송 완료');

            // 잠시 대기
            await new Promise(resolve => setTimeout(resolve, 2000));

            // 답지 전송
            await this.slack.files.uploadV2({
                channel_id: this.channel,
                file: fs.createReadStream(answerFile),
                filename: answerFile,
                title: `✅ 정답지 - ${today}`,
                initial_comment: `📋 **정답지 및 해설**\n시험 완료 후 확인해주세요!\n합격선: 70점 이상 🎯`
            });

            console.log('✅ 답지 전송 완료');
            console.log('🎉 모든 파일 전송 성공!');
            
        } catch (error) {
            console.error('❌ Slack 전송 중 오류:', error);
            throw error;
        }
    }

    async sendMessage(text) {
        try {
            await this.slack.chat.postMessage({
                channel: this.channel,
                text: text
            });
            console.log('✅ 메시지 전송 완료');
        } catch (error) {
            console.error('❌ 메시지 전송 실패:', error);
            throw error;
        }
    }
}

// 실행부
if (require.main === module) {
    const token = process.env.SLACK_BOT_TOKEN;
    const channel = process.env.SLACK_CHANNEL_ID;
    
    if (!token || !channel) {
        console.error('❌ Slack 토큰 또는 채널 ID가 설정되지 않았습니다.');
        console.log('다음 환경변수를 설정해주세요:');
        console.log('- SLACK_BOT_TOKEN');
        console.log('- SLACK_CHANNEL_ID');
        process.exit(1);
    }

    const sender = new SlackSender(token, channel);
    
    // 가장 최근 생성된 시험지 파일 찾기
    const today = new Date().toISOString().split('T')[0];
    const examFile = `exam_${today}.md`;
    const answerFile = `answers_${today}.md`;
    
    // 파일 존재 확인
    if (!fs.existsSync(examFile) || !fs.existsSync(answerFile)) {
        console.error('❌ 시험지 파일을 찾을 수 없습니다.');
        console.log('먼저 exam-generator.js를 실행하여 시험지를 생성해주세요.');
        process.exit(1);
    }
    
    sender.sendExamFiles(examFile, answerFile)
        .then(() => console.log('🎉 전송 완료'))
        .catch(error => console.error('💥 전송 실패:', error));
}

module.exports = SlackSender;
