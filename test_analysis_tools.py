from analysis_tools import build_analysis_row


def test_build_analysis_row_returns_required_columns():
    def fake_llm(_payload):
        return {
            "核心卖点": "三防机身，长续航",
            "优点评炼": "续航长，机身耐用",
            "缺点评炼": "外观偏厚重",
            "综合分析": "适合户外和耐用场景",
            "竞品定位": "中低价三防竞品",
        }

    row = build_analysis_row(
        brand="Blackview",
        product={
            "asin": "B0TEST1234",
            "url": "https://www.amazon.com/dp/B0TEST1234",
            "title": "Blackview Example",
            "price": "$199.99",
            "rating": "4.4 out of 5 stars",
            "review_count": "321",
        },
        review_summary={
            "pros": ["续航长"],
            "cons": ["偏厚重"],
            "overall": "适合户外使用",
        },
        llm_call=fake_llm,
    )

    assert row == {
        "品牌": "Blackview",
        "ASIN": "B0TEST1234",
        "url": "https://www.amazon.com/dp/B0TEST1234",
        "商品标题": "Blackview Example",
        "价格": "$199.99",
        "评分": "4.4 out of 5 stars",
        "评论数": "321",
        "核心卖点": "三防机身，长续航",
        "优点评炼": "续航长",
        "缺点评炼": "偏厚重",
        "综合分析": "适合户外使用",
        "竞品定位": "中低价三防竞品",
    }


def test_build_analysis_row_uses_review_summary_for_review_columns_when_llm_omits_them():
    def fake_llm(_payload):
        return {
            "核心卖点": "三防机身，长续航",
            "竞品定位": "中低价三防竞品",
        }

    row = build_analysis_row(
        brand="Blackview",
        product={
            "asin": "B0TEST1234",
            "url": "https://www.amazon.com/dp/B0TEST1234",
            "title": "Blackview Example",
            "price": "$199.99",
            "rating": "4.4 out of 5 stars",
            "review_count": "321",
        },
        review_summary={
            "pros": ["续航长", "机身耐用"],
            "cons": ["外观偏厚重"],
            "overall": "适合户外和耐用场景",
        },
        llm_call=fake_llm,
    )

    assert row["核心卖点"] == "三防机身，长续航"
    assert row["优点评炼"] == "续航长；机身耐用"
    assert row["缺点评炼"] == "外观偏厚重"
    assert row["综合分析"] == "适合户外和耐用场景"
    assert row["竞品定位"] == "中低价三防竞品"
