// Central CI repository. The Flutter repository receives no CI files.
def checkoutSources() {
    dir('ci-platform') {
        deleteDir()
        def revision = checkout(changelog: false, poll: false, scm: scm)
        if (env.CI_COMMIT) { sh 'git checkout --detach "$CI_COMMIT"' }
        else { env.CI_COMMIT = revision.GIT_COMMIT }
        env.CI_ROOT = pwd()
    }
    dir('app') {
        deleteDir()
        def firstCheckout = !env.APP_COMMIT
        def revision = checkout(changelog: firstCheckout, poll: firstCheckout, scm: [
            $class: 'GitSCM',
            branches: [[name: firstCheckout ? (params.APP_BRANCH.startsWith("refs/heads/") ? params.APP_BRANCH : "*/${params.APP_BRANCH}") : env.APP_COMMIT]],
            userRemoteConfigs: [[url: params.APP_REPOSITORY_URL, credentialsId: params.APP_CREDENTIALS_ID ?: '']],
            extensions: []
        ])
        if (firstCheckout) { env.APP_COMMIT = revision.GIT_COMMIT }
        if (!(env.APP_COMMIT ==~ /[0-9a-fA-F]{40,64}/)) { error('Missing application commit') }
        sh 'test "$(git rev-parse HEAD)" = "$APP_COMMIT"'
    }
}
def linuxRun(String action, String platform = '') {
    withEnv(["CI_ACTION=${action}", "CI_PLATFORM=${platform}"]) {
        sh '''
            set -eu
            set -- "$CI_ACTION" --project "$WORKSPACE/app"
            if [ -n "$CI_PLATFORM" ]; then set -- "$@" --platform "$CI_PLATFORM"; fi
            docker run --rm --volumes-from jenkins \
              -v flutter-pub-cache:/root/.pub-cache -v gradle-cache:/root/.gradle \
              -v flutter-ndk-cache:/opt/android-sdk/ndk \
              -e PYTHONDONTWRITEBYTECODE=1 -e ENVIRONMENT -e BUILD_MODE \
              -e APP_NAME -e API_BASE_URL -e ANDROID_APPLICATION_ID -e IOS_BUNDLE_ID \
              -e ANDROID_FLAVOR -e IOS_SCHEME -e ANDROID_RELEASE_SIGNING \
              -e ANDROID_KEYSTORE_FILE -e ANDROID_STORE_PASSWORD -e ANDROID_KEY_ALIAS -e ANDROID_KEY_PASSWORD \
              -w "$WORKSPACE" "$FLUTTER_IMAGE" \
              python3 "$CI_ROOT/scripts/build.py" "$@"
        '''
    }
}
def archiveOutput(String platform) {
    def output = "app/build/ci/${params.ENVIRONMENT}/${params.BUILD_MODE}/${platform}"
    def expected = "${params.ENVIRONMENT} ${params.BUILD_MODE} ${platform}"
    if (!fileExists("${output}/SUCCESS") || readFile("${output}/SUCCESS").trim() != expected) {
        error("Missing success marker for ${platform}")
    }
    def artifact = platform == 'web' ? 'app.zip' :
        (platform == 'android' ? (params.BUILD_MODE == 'debug' ? 'app.apk' : 'app.aab') :
        (params.BUILD_MODE == 'debug' ? 'app.zip' : 'app.ipa'))
    archiveArtifacts artifacts: "${output}/${artifact}", fingerprint: true, allowEmptyArchive: false
}
pipeline {
    agent none
    options {
        timestamps()
        disableConcurrentBuilds()
        skipDefaultCheckout(true)
        timeout(time: 120, unit: 'MINUTES')
    }
    // Define all public values in the job's Configure page.
    environment {
        ENVIRONMENT = "${params.ENVIRONMENT}"
        BUILD_MODE = "${params.BUILD_MODE}"
        APP_NAME = "${params.APP_NAME}"
        API_BASE_URL = "${params.API_BASE_URL}"
        ANDROID_APPLICATION_ID = "${params.ANDROID_APPLICATION_ID}"
        IOS_BUNDLE_ID = "${params.IOS_BUNDLE_ID}"
        FLUTTER_IMAGE = "${params.FLUTTER_IMAGE}"
        ANDROID_RELEASE_SIGNING = "${params.ANDROID_RELEASE_SIGNING ?: ''}"
        ANDROID_FLAVOR = "${params.ANDROID_FLAVOR ?: ''}"
        IOS_TEAM_ID = "${params.IOS_TEAM_ID ?: ''}"
        IOS_EXPORT_METHOD = "${params.IOS_EXPORT_METHOD ?: ''}"
        IOS_SIGNING_STYLE = "${params.IOS_SIGNING_STYLE ?: ''}"
        IOS_PROFILE_NAME = "${params.IOS_PROFILE_NAME ?: ''}"
        IOS_CODE_SIGN_IDENTITY = "${params.IOS_CODE_SIGN_IDENTITY ?: ''}"
        IOS_RELEASE_SIGNING = "${params.IOS_RELEASE_SIGNING ?: ''}"
        IOS_SCHEME = "${params.IOS_SCHEME ?: 'Runner'}"
        PYTHONDONTWRITEBYTECODE = '1'
    }
    stages {
        stage('Validate Job Settings') {
            steps {
                script {
                    if (!(params.ENVIRONMENT in ['testing', 'staging', 'production'])) { error('Configure ENVIRONMENT') }
                    if (!(params.BUILD_MODE in ['debug', 'release'])) { error('Configure BUILD_MODE') }
                    if (!(params.PLATFORM in ['web', 'android', 'ios', 'all'])) { error('Configure PLATFORM') }
                    if (!(params.APP_BRANCH ==~ /[A-Za-z0-9_][A-Za-z0-9_.\/-]*/) ||
                        (params.APP_BRANCH.startsWith('refs/') && !params.APP_BRANCH.startsWith('refs/heads/')) ||
                        params.APP_BRANCH.contains('..') || params.APP_BRANCH.contains('//') ||
                        params.APP_BRANCH.endsWith('/') || params.APP_BRANCH.endsWith('.') ||
                        params.APP_BRANCH.tokenize('/').any { it.startsWith('.') || it.endsWith('.lock') }) {
                        error('APP_BRANCH must be one literal branch name')
                    }
                    if (!(params.APP_REPOSITORY_URL ==~ /https:\/\/[A-Za-z0-9.-]+(?::[0-9]+)?\/[A-Za-z0-9_.\/-]+/) &&
                        !(params.APP_REPOSITORY_URL ==~ /[A-Za-z0-9._-]+@[A-Za-z0-9.-]+:[A-Za-z0-9_.\/-]+/) &&
                        !(params.APP_REPOSITORY_URL ==~ /ssh:\/\/[A-Za-z0-9._-]+@[A-Za-z0-9.-]+(?::[0-9]+)?\/[A-Za-z0-9_.\/-]+/)) {
                        error('Configure a Git HTTPS/SSH URL without embedded secrets')
                    }
                    for (key in ['APP_NAME', 'API_BASE_URL', 'ANDROID_APPLICATION_ID', 'IOS_BUNDLE_ID']) {
                        if (!params[key]?.trim() || params[key] != params[key].trim()) { error("Configure ${key}") }
                    }
                    for (key in ['APP_CREDENTIALS_ID', 'ANDROID_KEYSTORE_CREDENTIAL_ID', 'ANDROID_STORE_PASSWORD_CREDENTIAL_ID', 'ANDROID_KEY_ALIAS_CREDENTIAL_ID', 'ANDROID_KEY_PASSWORD_CREDENTIAL_ID', 'IOS_P12_CREDENTIAL_ID', 'IOS_PASSWORD_CREDENTIAL_ID', 'IOS_PROFILE_CREDENTIAL_ID']) {
                        if (!((params[key] ?: '') ==~ /[A-Za-z0-9_.-]*/)) { error("Invalid ${key}") }
                    }
                    if (params.PLATFORM != 'ios' && !(params.LINUX_AGENT_LABEL ==~ /[A-Za-z0-9_.-]+/)) {
                        error('Configure LINUX_AGENT_LABEL')
                    }
                    if (params.PLATFORM in ['ios', 'all'] && !(params.MACOS_AGENT_LABEL ==~ /[A-Za-z0-9_.-]+/)) {
                        error('Configure MACOS_AGENT_LABEL')
                    }
                    if (!(params.FLUTTER_IMAGE ==~ /[A-Za-z0-9][A-Za-z0-9_.:\/@-]*/)) { error('Configure FLUTTER_IMAGE') }
                }
            }
        }
        stage('Linux Builds') {
            when { beforeAgent true; expression { params.PLATFORM in ['web', 'android', 'all'] } }
            agent { label "${params.LINUX_AGENT_LABEL}" }
            stages {
                stage('Checkout Linux') { steps { script { checkoutSources() } } }
                stage('Validate App Configuration') { steps { script { linuxRun('validate') } } }
                stage('Analyze and Test') { steps { script { linuxRun('quality') } } }
                stage('Web') {
                    when { expression { params.PLATFORM in ['web', 'all'] } }
                    steps { script { linuxRun('build', 'web'); archiveOutput('web') } }
                }
                stage('Android') {
                    when { expression { params.PLATFORM in ['android', 'all'] } }
                    steps {
                        script {
                            if (params.BUILD_MODE == 'release' && params.ANDROID_RELEASE_SIGNING == 'jenkins') {
                                for (key in ['ANDROID_KEYSTORE_CREDENTIAL_ID', 'ANDROID_STORE_PASSWORD_CREDENTIAL_ID', 'ANDROID_KEY_ALIAS_CREDENTIAL_ID', 'ANDROID_KEY_PASSWORD_CREDENTIAL_ID']) {
                                    if (!params[key]) { error("Configure ${key}") }
                                }
                                withCredentials([
                                    file(credentialsId: params.ANDROID_KEYSTORE_CREDENTIAL_ID, variable: 'ANDROID_KEYSTORE_FILE'),
                                    string(credentialsId: params.ANDROID_STORE_PASSWORD_CREDENTIAL_ID, variable: 'ANDROID_STORE_PASSWORD'),
                                    string(credentialsId: params.ANDROID_KEY_ALIAS_CREDENTIAL_ID, variable: 'ANDROID_KEY_ALIAS'),
                                    string(credentialsId: params.ANDROID_KEY_PASSWORD_CREDENTIAL_ID, variable: 'ANDROID_KEY_PASSWORD')
                                ]) { linuxRun('build', 'android') }
                            } else { linuxRun('build', 'android') }
                            archiveOutput('android')
                        }
                    }
                }
            }
        }
        stage('iOS Build') {
            when { beforeAgent true; expression { params.PLATFORM in ['ios', 'all'] } }
            agent { label "${params.MACOS_AGENT_LABEL}" }
            environment { LANG = 'en_US.UTF-8'; LC_ALL = 'en_US.UTF-8' }
            stages {
                stage('Checkout macOS') { steps { script { checkoutSources() } } }
                stage('Validate and Test iOS') {
                    steps {
                        sh '''
                            set -eu
                            export BUNDLE_GEMFILE="$CI_ROOT/Gemfile"
                            bundle check || bundle install
                            python3 "$CI_ROOT/scripts/build.py" validate --project "$WORKSPACE/app"
                            python3 "$CI_ROOT/scripts/build.py" quality --project "$WORKSPACE/app"
                        '''
                    }
                }
                stage('Build iOS Artifact') {
                    steps {
                        script {
                            def command = '''
                                set +x
                                set -eu
                                export BUNDLE_GEMFILE="$CI_ROOT/Gemfile"
                                python3 "$CI_ROOT/scripts/build.py" build --project "$WORKSPACE/app" --platform ios
                            '''
                            if (params.BUILD_MODE == 'release' && params.IOS_RELEASE_SIGNING == 'jenkins') {
                                for (key in ['IOS_P12_CREDENTIAL_ID', 'IOS_PASSWORD_CREDENTIAL_ID', 'IOS_PROFILE_CREDENTIAL_ID']) {
                                    if (!params[key]) { error("Configure ${key}") }
                                }
                                withCredentials([
                                    file(credentialsId: params.IOS_P12_CREDENTIAL_ID, variable: 'IOS_P12_FILE'),
                                    string(credentialsId: params.IOS_PASSWORD_CREDENTIAL_ID, variable: 'IOS_P12_PASSWORD'),
                                    file(credentialsId: params.IOS_PROFILE_CREDENTIAL_ID, variable: 'IOS_PROFILE_FILE')
                                ]) { sh command }
                            } else { sh command }
                            archiveOutput('ios')
                        }
                    }
                }
            }
        }
    }
    post {
        success { echo "Built app commit ${env.APP_COMMIT}: ${params.APP_NAME}, ${params.ENVIRONMENT}/${params.BUILD_MODE}/${params.PLATFORM}" }
        failure { echo 'Central build failed; inspect the stage error.' }
    }
}
