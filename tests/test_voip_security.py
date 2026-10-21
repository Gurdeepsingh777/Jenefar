from jenefar.voip_security import analyze_source


def test_flags_copy_and_signed_packet_length():
    source = """
void parse_rtp_packet(char *buffer, int packet_size) {
    char local_buffer[1024];
    memcpy(local_buffer, buffer, packet_size);
}
"""
    findings = analyze_source(source)
    ids = {finding.rule_id for finding in findings}
    assert {"VOIP001", "VOIP002", "VOIP004"} <= ids


def test_ignores_comment_only_examples():
    source = "// memcpy(dst, src, length)\n/* parse_rtp_packet(buffer); */\n"
    assert analyze_source(source) == []


def test_flags_possible_length_multiplication_overflow():
    findings = analyze_source("size_t bytes = packet_size * item_count;")
    assert any(f.rule_id == "VOIP003" for f in findings)


def test_empty_source_has_no_findings():
    assert analyze_source("") == []
