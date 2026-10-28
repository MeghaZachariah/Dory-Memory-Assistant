import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import 'settings.dart';

class DoryApiException implements Exception {
  DoryApiException(this.message);
  final String message;
  @override
  String toString() => message;
}

/// The session ended (signed out elsewhere, or expired): the app goes back to the login screen.
class DoryAuthException extends DoryApiException {
  DoryAuthException(super.message);
}

class ChatReply {
  ChatReply({required this.reply, required this.status, required this.route, required this.blocked});
  final String reply;
  final String status; // answered | unknown | refused
  final String route; // memory | medication | override | error
  final bool blocked;
}

class EveningReply {
  EveningReply({required this.say, required this.done, required this.factsSaved});
  final String say;
  final bool done;
  final int factsSaved;
}

/// Talks to the Dory server (backend/api/main.py).
class DoryApi {
  DoryApi(this.settings);
  final DorySettings settings;
  static const _timeout = Duration(seconds: 25);

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (settings.token.isNotEmpty) 'X-Dory-Token': settings.token,
        if (settings.sessionToken.isNotEmpty) 'Authorization': 'Bearer ${settings.sessionToken}',
      };

  Uri _url(String path, [Map<String, String>? query]) =>
      Uri.parse('${settings.serverUrl}$path').replace(queryParameters: query);

  Future<Map<String, dynamic>> _send(Future<http.Response> request) async {
    final http.Response res;
    try {
      res = await request.timeout(_timeout);
    } catch (e) {
      throw DoryApiException('Could not reach the Dory server at ${settings.serverUrl} ($e)');
    }
    if (res.statusCode == 401) throw DoryAuthException(_detail(res) ?? 'Please sign in again');
    if (res.statusCode != 200) {
      throw DoryApiException(_detail(res) ?? 'Server error ${res.statusCode}');
    }
    return jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>;
  }

  /// The server's own explanation ({"detail": "..."}), if it sent one.
  String? _detail(http.Response res) {
    try {
      return (jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>)['detail']?.toString();
    } catch (_) {
      return null;
    }
  }

  // --- Family account ---------------------------------------------------------

  /// Signs in with the family's account (made on the Dory website). Returns the session
  /// token and the account: {email, person_id, person_name, family_names, caregivers}.
  Future<(String, Map<String, dynamic>)> login(String email, String password) async {
    final http.Response res;
    try {
      res = await http
          .post(
            _url('/auth/login'),
            headers: _headers,
            body: jsonEncode({'email': email.trim(), 'password': password, 'device': 'Dory phone app'}),
          )
          .timeout(_timeout);
    } catch (e) {
      throw DoryApiException('Could not reach the Dory server at ${settings.serverUrl}. Check the address and Wi-Fi.');
    }
    if (res.statusCode != 200) throw DoryApiException(_detail(res) ?? 'Could not sign in (${res.statusCode})');
    final d = jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>;
    return (d['token'] as String, d['account'] as Map<String, dynamic>);
  }

  /// The signed-in account. Throws DoryAuthException if the session has ended.
  Future<Map<String, dynamic>> me() => _send(http.get(_url('/auth/me'), headers: _headers));

  Future<void> logout() async {
    try {
      await http.post(_url('/auth/logout'), headers: _headers).timeout(const Duration(seconds: 5));
    } catch (_) {
      // Signing out on the phone works even when the server can't be reached.
    }
  }

  Future<bool> health() async {
    try {
      final data = await _send(http.get(_url('/health')));
      return data['ok'] == true;
    } catch (_) {
      return false;
    }
  }

  /// [history]: the conversation so far in this call, [{"speaker": "Dory" | name, "text": ...}],
  /// so Dory can follow it ("no", "what about yesterday?").
  Future<ChatReply> chat(String message, {List<Map<String, String>> history = const []}) async {
    final d = await _send(http.post(
      _url('/chat'),
      headers: _headers,
      body: jsonEncode({'person_id': settings.personId, 'message': message, 'history': history}),
    ));
    return ChatReply(
      reply: d['reply'] as String? ?? '',
      status: d['status'] as String? ?? 'unknown',
      route: d['route'] as String? ?? 'error',
      blocked: d['blocked'] as bool? ?? false,
    );
  }

  /// turns: [{"speaker": "Dory" | name, "text": "..."}]. Send [] to start the evening call.
  Future<EveningReply> eveningTurn(List<Map<String, String>> turns) async {
    final d = await _send(http.post(
      _url('/evening/turn'),
      headers: _headers,
      body: jsonEncode({'person_id': settings.personId, 'turns': turns}),
    ));
    return EveningReply(
      say: d['say'] as String? ?? '',
      done: d['done'] as bool? ?? true,
      factsSaved: (d['facts_saved'] as num?)?.toInt() ?? 0,
    );
  }

  /// The evening call ended before Dory's goodbye: save the memories from what was said so far.
  Future<void> finishEvening(List<Map<String, String>> turns) async {
    await _send(http.post(
      _url('/checkin/evening/finish'),
      headers: _headers,
      body: jsonEncode({
        'person_id': settings.personId,
        'transcript': [
          for (final t in turns) {'role': t['speaker'] == 'Dory' ? 'dory' : 'person', 'text': t['text'] ?? ''},
        ],
      }),
    ));
  }

  Future<String> briefing() async {
    final d = await _send(http.get(_url('/briefing/${settings.personId}'), headers: _headers));
    return d['text'] as String? ?? '';
  }

  // --- Family voice (optional) ------------------------------------------------

  Future<FamilyVoiceStatus> voiceStatus() async =>
      FamilyVoiceStatus.fromJson(await _send(http.get(_url('/voice/${settings.personId}'), headers: _headers)));

  /// Uploads the family member's recording (WAV). They must have agreed to it.
  Future<FamilyVoiceStatus> uploadVoice(Uint8List wav, String speakerName) async {
    final res = await http
        .put(
          _url('/voice/${settings.personId}', {'speaker_name': speakerName, 'consent': 'true'}),
          headers: {..._headers, 'Content-Type': 'audio/wav'},
          body: wav,
        )
        .timeout(const Duration(seconds: 90));
    if (res.statusCode != 200) {
      final detail = (jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>)['detail'];
      throw DoryApiException(detail?.toString() ?? 'Server error ${res.statusCode}');
    }
    return FamilyVoiceStatus.fromJson(jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>);
  }

  Future<void> deleteVoice() async {
    await _send(http.delete(_url('/voice/${settings.personId}'), headers: _headers));
  }

  /// [text] spoken in the family voice, as WAV bytes. Null on any problem: use the phone voice.
  Future<Uint8List?> speakAsFamily(String text) async {
    try {
      final res = await http
          .post(
            _url('/voice/${settings.personId}/speak'),
            headers: _headers,
            body: jsonEncode({'text': text, 'locale': settings.locale}),
          )
          .timeout(const Duration(seconds: 20));
      return res.statusCode == 200 ? res.bodyBytes : null;
    } catch (_) {
      return null;
    }
  }
}

class FamilyVoiceStatus {
  FamilyVoiceStatus({required this.enabled, required this.speakerName, required this.serverOnline});
  final bool enabled;
  final String? speakerName;
  final bool serverOnline;

  factory FamilyVoiceStatus.fromJson(Map<String, dynamic> d) => FamilyVoiceStatus(
        enabled: d['enabled'] as bool? ?? false,
        speakerName: d['speaker_name'] as String?,
        serverOnline: d['server_online'] as bool? ?? false,
      );
}
