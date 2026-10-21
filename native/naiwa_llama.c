/*
 * naiwa_llama.c —— 奶娃 Agent 的 llama.cpp 薄封装。
 *
 * 为什么要这层 C：
 *   llama.cpp 的 C API 结构体布局随版本变化（llama_context_params 尤其多），
 *   在 Python 里用 ctypes 直接按值传结构体，换一版 llama.cpp 就会内存踩踏。
 *   所以把不稳定的部分编译进 .so，只对 Python 暴露 4 个稳定函数：
 *
 *     void  naiwa_backend_init(void);
 *     void *naiwa_load(const char *path, int n_threads);
 *     void  naiwa_free(void *handle);
 *     int   naiwa_generate(void *h, const char *prompt, int max_tokens,
 *                          float temp, float top_p, int n_ctx, int n_threads,
 *                          naiwa_token_cb cb, void *user, char *err, int errlen);
 *
 * 每次生成都新建一个 context、用完立刻释放：避开了 llama_kv_self_clear /
 * llama_memory_clear 这类改名频繁的接口。模型权重只加载一次，代价很小。
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "llama.h"

typedef int (*naiwa_token_cb)(const char *piece, void *user);

typedef struct {
    struct llama_model *model;
    const struct llama_vocab *vocab;
} naiwa_handle;

static void set_err(char *err, int errlen, const char *msg) {
    if (err && errlen > 0) {
        snprintf(err, (size_t) errlen, "%s", msg);
    }
}

void naiwa_backend_init(void) {
    llama_backend_init();
}

void *naiwa_load(const char *path, int n_threads) {
    (void) n_threads;
    if (!path) {
        return NULL;
    }
    struct llama_model_params mparams = llama_model_default_params();
    mparams.use_mmap = true;

#ifdef NAIWA_LLAMA_OLD_API
    struct llama_model *model = llama_load_model_from_file(path, mparams);
#else
    struct llama_model *model = llama_model_load_from_file(path, mparams);
#endif
    if (!model) {
        return NULL;
    }
    naiwa_handle *h = (naiwa_handle *) calloc(1, sizeof(naiwa_handle));
    if (!h) {
        llama_model_free(model);
        return NULL;
    }
    h->model = model;
    h->vocab = llama_model_get_vocab(model);
    return h;
}

void naiwa_free(void *handle) {
    naiwa_handle *h = (naiwa_handle *) handle;
    if (!h) {
        return;
    }
    if (h->model) {
        llama_model_free(h->model);
    }
    free(h);
}

int naiwa_generate(void *handle,
                   const char *prompt,
                   int max_tokens,
                   float temp,
                   float top_p,
                   int n_ctx,
                   int n_threads,
                   naiwa_token_cb cb,
                   void *user,
                   char *err,
                   int errlen) {
    naiwa_handle *h = (naiwa_handle *) handle;
    if (!h || !h->model || !h->vocab) {
        set_err(err, errlen, "模型未加载");
        return -1;
    }
    if (!prompt) {
        set_err(err, errlen, "prompt 为空");
        return -1;
    }

    struct llama_context_params cparams = llama_context_default_params();
    cparams.n_ctx = (uint32_t) (n_ctx > 0 ? n_ctx : 2048);
    cparams.n_threads = (int32_t) (n_threads > 0 ? n_threads : 4);
    cparams.n_threads_batch = cparams.n_threads;
    cparams.n_batch = 256;

    struct llama_context *ctx = llama_init_from_model(h->model, cparams);
    if (!ctx) {
        set_err(err, errlen, "创建推理上下文失败（内存不足？）");
        return -2;
    }

    int status = 0;
    const char *text = prompt;
    int text_len = (int) strlen(text);

    /* 第一遍问需要多少 token，第二遍真正切分 */
    int n_tokens = -llama_tokenize(h->vocab, text, text_len, NULL, 0, true, true);
    if (n_tokens <= 0) {
        set_err(err, errlen, "分词失败");
        llama_free(ctx);
        return -3;
    }
    llama_token *tokens = (llama_token *) malloc((size_t) n_tokens * sizeof(llama_token));
    if (!tokens) {
        set_err(err, errlen, "内存不足");
        llama_free(ctx);
        return -4;
    }
    if (llama_tokenize(h->vocab, text, text_len, tokens, n_tokens, true, true) < 0) {
        set_err(err, errlen, "分词失败（缓冲区不足）");
        free(tokens);
        llama_free(ctx);
        return -5;
    }

    if (n_tokens >= (int) cparams.n_ctx) {
        set_err(err, errlen, "上下文超长，请清空对话或调大上下文窗口");
        free(tokens);
        llama_free(ctx);
        return -6;
    }

    struct llama_batch batch = llama_batch_get_one(tokens, n_tokens);
    if (llama_decode(ctx, batch) != 0) {
        set_err(err, errlen, "预填充解码失败");
        free(tokens);
        llama_free(ctx);
        return -7;
    }
    free(tokens);

    struct llama_sampler *sampler = llama_sampler_chain_init(llama_sampler_chain_default_params());
    llama_sampler_chain_add(sampler, llama_sampler_init_top_k(40));
    llama_sampler_chain_add(sampler, llama_sampler_init_top_p(top_p > 0 ? top_p : 0.9f, 1));
    llama_sampler_chain_add(sampler, llama_sampler_init_temp(temp > 0 ? temp : 0.7f));
    llama_sampler_chain_add(sampler, llama_sampler_init_dist(LLAMA_DEFAULT_SEED));

    int produced = 0;
    char piece[512];

    for (int i = 0; i < max_tokens; i++) {
        llama_token id = llama_sampler_sample(sampler, ctx, -1);
        if (llama_vocab_is_eog(h->vocab, id)) {
            break;
        }
        int len = llama_token_to_piece(h->vocab, id, piece, (int) sizeof(piece) - 1, 0, true);
        if (len < 0) {
            break;
        }
        piece[len] = '\0';
        produced += 1;
        if (cb && cb(piece, user) != 0) {
            break;
        }
        struct llama_batch next = llama_batch_get_one(&id, 1);
        if (llama_decode(ctx, next) != 0) {
            set_err(err, errlen, "解码失败");
            status = -8;
            break;
        }
    }

    llama_sampler_free(sampler);
    llama_free(ctx);

    if (produced == 0 && status == 0) {
        set_err(err, errlen, "模型没有生成任何内容");
        return -9;
    }
    return status;
}
