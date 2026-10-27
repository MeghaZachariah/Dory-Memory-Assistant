import 'dart:async';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_recognition_error.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
import 'package:speech_to_text/speech_to_text.dart';

/// Listening and speaking, using Android's built-in engines (free, on the phone).
class Voice {
  final SpeechToText _stt = SpeechToText();
  final FlutterTts _tts = FlutterTts();
  bool _ready = false;
  String? _localeId;
  Completer<String>? _pending;
  String _lastWords = '';

  /// Called with each partial transcript while the person is speaking.
  void Function(String words)? onPartial;

  /// Set when the family voice is switched on: returns the line as WAV audio, or null
  /// (voice server off, language not supported...), in which case the phone voice speaks it.
  Future<Uint8List?> Function(String text)? familyVoice;
  final AudioPlayer _player = AudioPlayer();

  Future<bool> init(String locale) async {
    if (_ready) return true;
    _ready = await _stt.initialize(onStatus: _onStatus, onError: _onError);
    if (_ready) _localeId = await _matchLocale(locale);

    await _tts.awaitSpeakCompletion(true);
    final ttsOk = await _tts.isLanguageAvailable(locale);
    await _tts.setLanguage(ttsOk == true ? locale : 'en-US');
    await _tts.setSpeechRate(0.42); // a little slower than normal, easier to follow
    await _tts.setPitch(1.0);
    return _ready;
  }

  Future<String?> _matchLocale(String wanted) async {
    final norm = wanted.replaceAll('-', '_').toLowerCase();
    final locales = await _stt.locales();
    for (final l in locales) {
      if (l.localeId.replaceAll('-', '_').toLowerCase() == norm) return l.localeId;
    }
    final lang = norm.split('_').first;
    for (final l in locales) {
      if (l.localeId.toLowerCase().startsWith(lang)) return l.localeId;
    }
    return (await _stt.systemLocale())?.localeId;
  }

  Future<void> speak(String text) async {
    if (text.trim().isEmpty) return;
    final audio = await familyVoice?.call(text);
    if (audio != null && await play(audio)) return;
    await _tts.speak(text);
  }

  /// Plays WAV bytes to the end. False if playback failed.
  Future<bool> play(Uint8List wav) async {
    try {
      final done = _player.onPlayerComplete.first;
      await _player.play(BytesSource(wav, mimeType: 'audio/wav'));
      await done.timeout(const Duration(minutes: 2));
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Listens once. Returns what the person said, or '' if they said nothing.
  Future<String> listen(
      {Duration listenFor = const Duration(seconds: 20), Duration pauseFor = const Duration(seconds: 3)}) async {
    if (!_ready) return '';
    await _stt.cancel();
    _lastWords = '';
    final completer = Completer<String>();
    _pending = completer;
    try {
      await _stt.listen(
        onResult: _onResult,
        // ignore: deprecated_member_use
        listenFor: listenFor,
        // ignore: deprecated_member_use
        pauseFor: pauseFor,
        // ignore: deprecated_member_use
        localeId: _localeId,
      );
    } catch (_) {
      _finish();
    }
    // Safety net in case the engine never reports that it stopped.
    return completer.future.timeout(listenFor + const Duration(seconds: 5), onTimeout: () {
      _stt.stop();
      return _lastWords;
    });
  }

  void _onResult(SpeechRecognitionResult r) {
    _lastWords = r.recognizedWords;
    onPartial?.call(_lastWords);
    if (r.finalResult) _finish();
  }

  void _onStatus(String status) {
    if (status == SpeechToText.doneStatus || status == SpeechToText.notListeningStatus) {
      // Give a final result a moment to arrive before giving up.
      Future.delayed(const Duration(milliseconds: 400), _finish);
    }
  }

  void _onError(SpeechRecognitionError e) => _finish();

  void _finish() {
    final c = _pending;
    if (c != null && !c.isCompleted) {
      _pending = null;
      c.complete(_lastWords.trim());
    }
  }

  Future<void> stop() async {
    await _stt.cancel();
    await _tts.stop();
    await _player.stop();
    _finish();
  }
}
