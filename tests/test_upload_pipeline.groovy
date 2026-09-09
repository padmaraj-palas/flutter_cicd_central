// Run from the repository root with: groovy tests/test_upload_pipeline.groovy
// Parses the real Jenkinsfile and executes its upload helper with Jenkins steps stubbed.
def source = new File('Jenkinsfile').getText('UTF-8')
int cases = 0
['android': ['firebase', 'google', 'none'], 'ios': ['firebase', 'appstore', 'none']].each { platform, destinations ->
    destinations.each { destination ->
        [false, true].each { failInstall ->
            def events = []
            boolean bound = false
            def parameters = [("${platform.toUpperCase()}_UPLOAD_DESTINATION".toString()): destination,
                              FIREBASE_CREDENTIALS_ID: 'firebase-id', GOOGLE_PLAY_CREDENTIALS_ID: 'play-id',
                              APPSTORE_API_KEY_CREDENTIALS_ID: 'apple-id']
            def binding = new Binding([params: parameters])
            binding.setVariable('sh', { String command ->
                if (command.contains('bundle check || bundle install')) {
                    assert !bound
                    assert command.contains('scripts/upload')
                    events << 'install'
                    if (failInstall) { throw new IllegalStateException('install fixture failure') }
                } else {
                    assert bound
                    assert command.contains('scripts/upload.py')
                    events << 'upload'
                }
            })
            binding.setVariable('withEnv', { values, Closure body -> body.call() })
            binding.setVariable('file', { Map values -> values })
            binding.setVariable('withCredentials', { values, Closure body ->
                assert events == ['install']
                def expected = destination == 'firebase' ? ['firebase-id', 'FIREBASE_CREDENTIALS_FILE'] :
                               destination == 'google' ? ['play-id', 'GOOGLE_PLAY_CREDENTIALS_FILE'] :
                               ['apple-id', 'APPSTORE_API_KEY_FILE']
                assert values == [[credentialsId: expected[0], variable: expected[1]]]
                events << 'bind'
                bound = true
                try { body.call() } finally { bound = false }
            })
            binding.setVariable('error', { message -> throw new IllegalStateException(message) })
            def pipeline = new GroovyShell(binding).parse(source)
            boolean failed = false
            try { pipeline.uploadArtifact(platform) } catch (IllegalStateException failure) {
                assert failInstall && failure.message == 'install fixture failure'
                failed = true
            }
            assert !bound
            if (destination == 'none') {
                assert events.empty && !failed
            } else if (failInstall) {
                assert events == ['install'] && failed
            } else {
                assert events == ['install', 'bind', 'upload'] && !failed
            }
            cases++
        }
    }
}
println "Jenkins upload helper: ${cases} cases passed (Jenkins steps stubbed)."
