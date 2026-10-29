import 'package:flutter/material.dart';

/// Loading and mutation share one lock so an initial read cannot overwrite a tap.
class BookmarkButton extends StatefulWidget {
  final Future<bool> Function() read;
  final Future<void> Function() save;
  final Future<void> Function() remove;
  final String label;
  final Color color;
  const BookmarkButton({
    super.key,
    required this.read,
    required this.save,
    required this.remove,
    required this.label,
    required this.color,
  });

  @override
  State<BookmarkButton> createState() => _BookmarkButtonState();
}

class _BookmarkButtonState extends State<BookmarkButton> {
  bool _saved = false;
  bool _busy = true;
  bool _readFailed = false;

  @override
  void initState() {
    super.initState();
    _read();
  }

  Future<void> _read() async {
    try {
      final saved = await widget.read();
      if (mounted) {
        setState(() {
          _saved = saved;
          _readFailed = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _readFailed = true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _toggle() async {
    if (_busy) return;
    setState(() => _busy = true);
    if (_readFailed) {
      await _read();
      return;
    }
    try {
      if (_saved) {
        await widget.remove();
      } else {
        await widget.save();
      }
      if (!mounted) return;
      setState(() => _saved = !_saved);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(_saved ? '${widget.label} 저장했어요.' : '저장이 취소됐어요.'),
        ),
      );
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('저장하지 못했어요. 다시 시도해주세요.')));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => IconButton(
    tooltip: _readFailed
        ? '저장 상태 다시 확인'
        : (_saved ? '저장 취소' : '${widget.label} 저장'),
    isSelected: _saved,
    icon: Icon(
      _readFailed ? Icons.error_outline : Icons.bookmark_outline_rounded,
      color: widget.color,
    ),
    selectedIcon: Icon(Icons.bookmark_rounded, color: widget.color),
    onPressed: _busy ? null : _toggle,
  );
}
