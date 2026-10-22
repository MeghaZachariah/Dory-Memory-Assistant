import 'dart:convert';

import 'package:http/http.dart' as http;

import 'settings.dart';

class DoryApiException implements Exception {
  DoryApiException(this.message);
  final String message;
  @override
  String toString() => message;
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
    if (res.statusCode != 200) {
      throw DoryApiException('Server error ${res.statusCode}: ${res.body}');
    }
    return jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>;
  }

  Future<bool> health() async {
    try {
      final data = await _send(http.get(_url('/health')));
      return data['ok'] == true;
    } catch (_) {
      return false;
    }
  }

  Future<ChatReply> chat(String message) async {
    final d = await _send(http.post(
      _url('/chat'),
      headers: _headers,
      body: jsonEncode({'person_id': settings.personId, 'message': message}),
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

  Future<String> briefing() async {
    final d = await _send(http.get(_url('/briefing/${settings.personId}'), headers: _headers));
    return d['text'] as String? ?? '';
  }
}
