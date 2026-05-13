from copy import deepcopy
from functools import partial
import os
import logging

from jupyterhub_fancy_profiles import setup_ui
from oauthenticator.generic import GenericOAuthenticator
from textwrap import dedent
from tornado import web

log = logging.getLogger(__name__)

c.JupyterHub.authenticator_class = GenericOAuthenticator

c.GenericOAuthenticator.client_id = "jupyterhub-staging"
c.GenericOAuthenticator.client_secret = os.environ["KEYCLOAK_CLIENT_SECRET"]
c.GenericOAuthenticator.oauth_callback_url = "http://localhost:8000/hub/oauth_callback"

c.GenericOAuthenticator.authorize_url = (
    "http://localhost:8080/realms/test-realm/protocol/openid-connect/auth"
)
c.GenericOAuthenticator.token_url = (
    "http://localhost:8080/realms/test-realm/protocol/openid-connect/token"
)
c.GenericOAuthenticator.userdata_url = (
    "http://localhost:8080/realms/test-realm/protocol/openid-connect/userinfo"
)

c.GenericOAuthenticator.username_claim = "preferred_username"
c.GenericOAuthenticator.userdata_token_method = "GET"
c.GenericOAuthenticator.scope = ["openid", "profile", "email"]

c.Authenticator.enable_auth_state = True

c.GenericOAuthenticator.manage_groups = True
c.GenericOAuthenticator.auth_state_groups_key = "oauth_user.roles"

c.GenericOAuthenticator.allowed_groups = {"basic-user"}
c.GenericOAuthenticator.admin_groups = {"admin"}


# KubeSpawner
c.JupyterHub.spawner_class = "kubespawner.KubeSpawner"


async def pre_spawn_hook(spawner):
    groups = [g.name for g in spawner.user.groups]
    log.warning("PRE-SPAWN for %s | groups=%s", spawner.user.name, groups)


c.Spawner.pre_spawn_hook = pre_spawn_hook


# This is a custom function to filter the profile list based on the user's group membership.
# Borrowed from https://github.com/2i2c-org/infrastructure/blob/299737334aeff1b34805ebfd6073621c06fb6576/helm-charts/basehub/values.yaml#L1388


async def profile_list_allowed_groups_filter(original_profile_list, spawner):
    """
    Returns the initially configured profile_list filtered based on the
    user's JupyterHub group membership (populated by manage_groups).

    If `allowed_groups` isn't set for a profile/choice, it is available to
    everyone.  If the filtered list is empty the user gets a 403.
    """
    if spawner.user.name == "deployment-service-check":
        return original_profile_list

    groups = {g.name.casefold() for g in spawner.user.groups}
    log.warning("PROFILE FILTER for %s | groups=%s", spawner.user.name, groups)

    allowed_profiles = []
    for original_profile in original_profile_list:
        profile = deepcopy(original_profile)

        if "profile_options" in profile:
            for po in profile["profile_options"].values():
                if "unlisted_choice" in po:
                    uc_groups = po["unlisted_choice"].get("allowed_groups")
                    if uc_groups and not (
                        set(g.casefold() for g in uc_groups) & groups
                    ):
                        del po["unlisted_choice"]

                if "choices" in po:
                    new_choices = {}
                    for k, choice in po["choices"].items():
                        if "allowed_groups" not in choice:
                            new_choices[k] = choice
                        else:
                            allowed = {g.casefold() for g in choice["allowed_groups"]}
                            if allowed & groups:
                                new_choices[k] = choice
                    po["choices"] = new_choices

        if "allowed_groups" not in profile:
            allowed_profiles.append(profile)
        else:
            allowed = {g.casefold() for g in profile["allowed_groups"]}
            if allowed & groups:
                log.warning(
                    "PROFILE FILTER allowing %s for %s",
                    profile["display_name"],
                    spawner.user.name,
                )
                allowed_profiles.append(profile)

    if not allowed_profiles:
        error_msg = dedent(f"""
            Your JupyterHub group membership is insufficient to launch any server profiles.

            JupyterHub groups you are a member of: {', '.join(groups)}.

            If you recently joined a group, log out and log back in to refresh.
        """)
        raise web.HTTPError(403, error_msg)

    return allowed_profiles


_static_profile_list = [
    {
        "display_name": "CPU only usage",
        "description": "For use with just CPU, no GPU",
        "default": True,
        "profile_options": {
            "image": {
                "display_name": "Image",
                "dynamic_image_building": {"enabled": True},
                "unlisted_choice": {
                    "enabled": True,
                    "display_name": "Custom image",
                    "validation_regex": "^.+:.+$",
                    "validation_message": "Must be a publicly available docker image, of form <image-name>:<tag>",
                    "display_name_in_choices": "Specify an existing docker image",
                    "description_in_choices": "Use a pre-existing docker image from a public docker registry",
                    "kubespawner_override": {"image": "{value}"},
                },
                "choices": {
                    "pangeo": {
                        "display_name": "Pangeo Notebook Image",
                        "description": "Python image with scientific, dask and geospatial tools",
                        "kubespawner_override": {
                            "image": "pangeo/pangeo-notebook:2023.09.11"
                        },
                    },
                    "geospatial": {
                        "display_name": "Rocker Geospatial",
                        "description": "R image with RStudio, the tidyverse & Geospatial tools",
                        "default": True,
                        "slug": "geospatial",
                        "kubespawner_override": {
                            "image": "rocker/binder:4.3",
                            "default_url": "/rstudio",
                            "working_dir": "/home/rstudio",
                        },
                    },
                    "scipy": {
                        "display_name": "Jupyter SciPy Notebook",
                        "slug": "scipy",
                        "kubespawner_override": {
                            "image": "jupyter/scipy-notebook:2023-06-26"
                        },
                    },
                },
            },
            "resources": {
                "display_name": "Resource Allocation",
                "choices": {
                    "mem_2_7": {
                        "display_name": "2.7 GB RAM, upto 3.479 CPUs",
                        "description": "Use this for the workshop on 2023 September",
                        "kubespawner_override": {
                            "mem_guarantee": 1024,
                            "mem_limit": 2904451072,
                            "cpu_guarantee": 0.1,
                            "cpu_limit": 3.479,
                        },
                        "default": True,
                    },
                    "mem_5_4": {
                        "display_name": "5.4 GB RAM, upto 3.479 CPUs",
                        "allowed_groups": ["power-user"],
                        "kubespawner_override": {
                            "mem_guarantee": 1024,
                            "mem_limit": 5808902144,
                            "cpu_guarantee": 0.1,
                            "cpu_limit": 3.479,
                        },
                    },
                    "mem_10_8": {
                        "display_name": "10.8 GB RAM, upto 3.479 CPUs",
                        "allowed_groups": ["power-user"],
                        "kubespawner_override": {
                            "mem_guarantee": 1024,
                            "mem_limit": 11617804288,
                            "cpu_guarantee": 0.1,
                            "cpu_limit": 3.479,
                        },
                    },
                    "mem_21_6": {
                        "display_name": "21.6 GB RAM, upto 3.479 CPUs",
                        "allowed_groups": ["power-user"],
                        "description": "Large amount of RAM, might start slowly",
                        "kubespawner_override": {
                            "mem_guarantee": 1024,
                            "mem_limit": 23235608576,
                            "cpu_guarantee": 0.1,
                            "cpu_limit": 3.479,
                        },
                    },
                },
            },
        },
    },
    {
        "display_name": "GPU only usage",
        "description": "for use with GPU",
        "allowed_groups": ["gpu-user"],
        "profile_options": {
            "image": {
                "display_name": "Image",
                "dynamic_image_building": {"enabled": True},
                "unlisted_choice": {
                    "enabled": True,
                    "display_name": "Custom image",
                    "validation_regex": "^.+:.+$",
                    "validation_message": "Must be a publicly available docker image, of form <image-name>:<tag>",
                    "display_name_in_choices": "Specify an existing docker image",
                    "description_in_choices": "Use a pre-existing docker image from a public docker registry",
                    "kubespawner_override": {"image": "{value}"},
                },
                "choices": {
                    "pangeo": {
                        "display_name": "Pangeo Notebook Image",
                        "description": "Python image with scientific, dask and geospatial tools",
                        "kubespawner_override": {
                            "image": "pangeo/pangeo-notebook:2023.09.11"
                        },
                    },
                    "geospatial": {
                        "display_name": "Rocker Geospatial",
                        "description": "R image with RStudio, the tidyverse & Geospatial tools",
                        "default": True,
                        "slug": "geospatial",
                        "kubespawner_override": {
                            "image": "rocker/binder:4.3",
                            "default_url": "/rstudio",
                            "working_dir": "/home/rstudio",
                        },
                    },
                    "scipy": {
                        "display_name": "Jupyter SciPy Notebook",
                        "slug": "scipy",
                        "kubespawner_override": {
                            "image": "jupyter/scipy-notebook:2023-06-26"
                        },
                    },
                },
            },
            "resources": {
                "display_name": "Resource Allocation",
                "choices": {
                    "mem_2_7": {
                        "display_name": "2.7 GB RAM, upto 3.479 CPUs",
                        "description": "Use this for the workshop on 2023 September",
                        "kubespawner_override": {
                            "mem_guarantee": 1024,
                            "mem_limit": 2904451072,
                            "cpu_guarantee": 0.1,
                            "cpu_limit": 3.479,
                        },
                        "default": True,
                    },
                    "mem_5_4": {
                        "display_name": "5.4 GB RAM, upto 3.479 CPUs",
                        "kubespawner_override": {
                            "mem_guarantee": 1024,
                            "mem_limit": 5808902144,
                            "cpu_guarantee": 0.1,
                            "cpu_limit": 3.479,
                        },
                    },
                    "mem_10_8": {
                        "display_name": "10.8 GB RAM, upto 3.479 CPUs",
                        "kubespawner_override": {
                            "mem_guarantee": 1024,
                            "mem_limit": 11617804288,
                            "cpu_guarantee": 0.1,
                            "cpu_limit": 3.479,
                        },
                    },
                    "mem_21_6": {
                        "display_name": "21.6 GB RAM, upto 3.479 CPUs",
                        "description": "Large amount of RAM, might start slowly",
                        "kubespawner_override": {
                            "mem_guarantee": 1024,
                            "mem_limit": 23235608576,
                            "cpu_guarantee": 0.1,
                            "cpu_limit": 3.479,
                        },
                    },
                },
            },
        },
    },
]

c.KubeSpawner.profile_list = partial(
    profile_list_allowed_groups_filter, deepcopy(_static_profile_list)
)

# Setup jupyterhub_fancy_profiles
setup_ui(c)
