#!/usr/bin/env ruby
# Change only a disposable checkout. No environment files or new schemes are created.
require 'xcodeproj'
require 'rexml/document'
require 'pathname'

abort 'Usage: prepare-ios.rb PROJECT' unless ARGV.length == 1
root = File.realpath(ARGV[0])
name = ENV.fetch('APP_NAME', '')
bundle_id = ENV.fetch('IOS_BUNDLE_ID', '')
scheme_name = ENV.fetch('IOS_SCHEME', 'Runner')
scheme_name = 'Runner' if scheme_name.empty?
abort 'Invalid APP_NAME' unless name.match?(/\A[A-Za-z0-9][A-Za-z0-9 ._-]{0,79}\z/)
abort 'Invalid IOS_BUNDLE_ID' unless bundle_id.match?(/\A[A-Za-z0-9][A-Za-z0-9-]*(\.[A-Za-z0-9][A-Za-z0-9-]*)+\z/)
abort 'Invalid IOS_SCHEME' unless scheme_name.match?(/\A[A-Za-z][A-Za-z0-9_-]*\z/)
project_path = File.join(root, 'ios/Runner.xcodeproj')
abort 'Expected ios/Runner.xcodeproj' unless File.directory?(project_path)
abort 'Xcode project must stay inside the checkout' unless File.realpath(project_path).start_with?(root + File::SEPARATOR) && File.realpath(File.join(project_path, 'project.pbxproj')).start_with?(root + File::SEPARATOR)
project = Xcodeproj::Project.open(project_path)
runner = project.targets.find { |target| target.name == 'Runner' && target.product_type == 'com.apple.product-type.application' }
abort 'Expected a Runner application target' unless runner
abort 'App extensions/custom targets require a reviewed central adapter' unless project.targets.all? do |target|
  target == runner || target.product_type == 'com.apple.product-type.bundle.unit-test'
end
scheme_path = File.join(project_path, 'xcshareddata/xcschemes', "#{scheme_name}.xcscheme")
abort 'IOS_SCHEME must select an existing shared scheme' unless File.file?(scheme_path)
scheme = REXML::Document.new(File.read(scheme_path))
references = REXML::XPath.match(scheme, '//BuildableReference')
abort 'Selected scheme must build Runner' unless references.any? { |ref| ref.attributes['BlueprintIdentifier'] == runner.uuid }
%w[LaunchAction ArchiveAction].each do |action|
  config_name = scheme.root.elements[action]&.attributes&.[]('buildConfiguration')
  abort "Selected scheme lacks a valid #{action} configuration" unless runner.build_configurations.any? { |config| config.name == config_name }
end
# Custom plist locations are supported only when they resolve within this checkout.
plists = runner.build_configurations.map do |config|
  owner = project.build_configurations.find { |entry| entry.name == config.name }
  path = config.build_settings['INFOPLIST_FILE'] || owner&.build_settings&.[]('INFOPLIST_FILE')
  abort 'Generated or xcconfig-defined Info.plists require a reviewed central adapter' unless path.is_a?(String) && !path.empty?
  path = path.gsub('$(SRCROOT)', File.join(root, 'ios')).gsub('${SRCROOT}', File.join(root, 'ios'))
             .gsub('$(PROJECT_DIR)', File.join(root, 'ios')).gsub('${PROJECT_DIR}', File.join(root, 'ios'))
  abort 'Unresolved Info.plist build variable' if path.include?('$')
  path = File.expand_path(path, File.join(root, 'ios'))
  abort 'Info.plist must be an existing file inside the checkout' unless File.file?(path) && File.realpath(path).start_with?(root + File::SEPARATOR)
  path
end.uniq
# Localized display names can override Info.plist at runtime; do not silently ship an old name.
abort 'Localized InfoPlist.strings require a reviewed central app-name adapter' unless Dir.glob(File.join(root, 'ios/**/*.lproj/InfoPlist.strings')).empty?
# Read all inputs before saving; leave signing, namespace, dependencies and schemes intact.
contents = plists.to_h { |path| [path, Xcodeproj::Plist.read_from_path(path)] }
runner.build_configurations.each do |config|
  config.build_settings['PRODUCT_BUNDLE_IDENTIFIER'] = bundle_id
  config.build_settings['CI_APP_NAME'] = name
  config.build_settings['INFOPLIST_KEY_CFBundleDisplayName'] = name
end
contents.each do |path, info|
  info['CFBundleIdentifier'] = '$(PRODUCT_BUNDLE_IDENTIFIER)'
  info['CFBundleDisplayName'] = '$(CI_APP_NAME)'
  Xcodeproj::Plist.write_to_path(info, path)
end
project.save
puts 'Applied Jenkins app name and iOS bundle ID to the disposable checkout.'
