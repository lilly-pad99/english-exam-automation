 const fs = require('fs');
const path = require('path');

/**
 * 유틸리티 함수들
 */
class Utils {
    /**
     * 날짜를 YYYY-MM-DD 형식으로 포맷
     */
    static formatDate(date = new Date()) {
        return date.toISOString().split('T')[0];
    }

    /**
     * 파일이 존재하는지 확인
     */
    static fileExists(filePath) {
        return fs.existsSync(filePath);
    }

    /**
     * 디렉토리가 존재하지 않으면 생성
     */
    static ensureDirectoryExists(dirPath) {
        if (!fs.existsSync(dirPath)) {
            fs.mkdirSync(dirPath, { recursive: true });
            console.log(`📁 디렉토리 생성: ${dirPath}`);
        }
    }

    /**
     * 배열을 무작위로 섞기
     */
    static shuffleArray(array) {
        const shuffled = [...array];
        for (let i = shuffled.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
        }
        return shuffled;
    }

    /**
     * 환경변수 확인
     */
    static checkEnvironmentVariables(requiredVars) {
        const missing = [];
        
        requiredVars.forEach(varName => {
            if (!process.env[varName]) {
                missing.push(varName);
            }
        });

        if (missing.length > 0) {
            console.error('❌ 필수 환경변수가 설정되지 않았습니다:');
            missing.forEach(varName => {
                console.error(`  - ${varName}`);
            });
            return false;
        }

        return true;
    }

    /**
     * 로그 메시지 포맷터
     */
    static log(level, message, ...args) {
        const timestamp = new Date().toISOString();
        const emoji = {
            'info': 'ℹ️',
            'success': '✅',
            'warning': '⚠️',
            'error': '❌'
        };

        console.log(`${emoji[level] || '📝'} [${timestamp}] ${message}`, ...args);
    }

    /**
     * 파일 크기를 읽기 쉬운 형태로 변환
     */
    static formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';

        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));

        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    /**
     * 실행 시간 측정
     */
    static async measureExecutionTime(fn, label = 'Operation') {
        const startTime = Date.now();
        
        try {
            const result = await fn();
            const endTime = Date.now();
            const duration = endTime - startTime;
            
            console.log(`⏱️ ${label} 완료: ${duration}ms`);
            return result;
        } catch (error) {
            const endTime = Date.now();
            const duration = endTime - startTime;
            
            console.error(`💥 ${label} 실패 (${duration}ms):`, error.message);
            throw error;
        }
    }

    /**
     * 재시도 로직
     */
    static async retry(fn, maxAttempts = 3, delay = 1000) {
        for (let attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                return await fn();
            } catch (error) {
                if (attempt === maxAttempts) {
                    throw error;
                }
                
                console.log(`🔄 재시도 ${attempt}/${maxAttempts} (${delay}ms 후)`);
                await new Promise(resolve => setTimeout(resolve, delay));
            }
        }
    }
}

module.exports = Utils;
